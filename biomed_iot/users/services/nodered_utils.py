# Utility functions for Nodered
import os
import subprocess
import logging
import bcrypt
import docker
import requests
from biomed_iot.config_loader import config
from . import server_utils
from .mosquitto_utils import MqttClientManager
import datetime
import jwt


logger = logging.getLogger(__name__)


class NoderedContainer:
    def __init__(self, nodered_user_data):
        self.name = nodered_user_data.container_name
        self.port = nodered_user_data.container_port
        self.is_configured = nodered_user_data.is_configured
        self.nodered_data = nodered_user_data
        self.access_token = nodered_user_data.access_token
        self.state = 'none'
        self.docker_client = docker.from_env()
        self.container = self.get_existing_container()

    def get_existing_container(self):
        try:
            return self.docker_client.containers.get(self.name)
        except docker.errors.NotFound:
            return None

    @staticmethod
    def check_container_state_by_name(container_name):  # for the endpoint
        docker_client = docker.from_env()
        state = ''
        try:
            container = docker_client.containers.get(container_name)
            container.reload()
            container_status = container.status
            try:
                container_health = container.attrs['State']['Health']['Status']
            except KeyError:
                container_health = 'N/A'
            # Determine the current state based on status and health
            if container_status == 'running' and container_health == 'starting':
                state = 'starting'
            elif container_status == 'running' and container_health == 'healthy':
                state = 'running'
            elif container_status == 'exited' and container_health == 'unhealthy':
                state = 'stopped'
            else:
                state = 'unavailable'
            return state
        except docker.errors.NotFound:
            return 'not_found'

    def hash_password(self, password):
        """Was used before jwt token based auth was implemented."""
        # Generate salt
        salt = bcrypt.gensalt()
        # Hash the password
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')

    def create(self, user):
        influxdb_host = config.host.HOST_DOCKER_INTERNAL_IP
        influxdb_port = config.influxdb.INFLUX_PORT
        influxdb_protocol = "http"
        influxdb_url = f"{influxdb_protocol}://{influxdb_host}:{influxdb_port}"

        mqtt_client_manager = MqttClientManager(user)
        nodered_mqtt_client = mqtt_client_manager.get_nodered_client()

        if not nodered_mqtt_client:
            raise RuntimeError("No Node-RED MQTT client configured for this user")

        nodered_mqtt_username = nodered_mqtt_client.username
        nodered_mqtt_password = nodered_mqtt_client.password

        if self.container is None:  # Only create a new container if one doesn't already exist
            env = {
                'SECRET_KEY': self.access_token,  # for Token (JWT) based auth
                'INFLUXDB_ORG': config.influxdb.INFLUX_ORG_NAME,
                'INFLUXDB_BUCKET': user.influxuserdata.bucket_name,
                'INFLUXDB_TOKEN': user.influxuserdata.bucket_token,
                'INFLUXDB_HOST': influxdb_host,
                'INFLUXDB_PORT': influxdb_port,
                'INFLUXDB_PROTOCOL': influxdb_protocol,
                'INFLUXDB_URL': influxdb_url,
                'MQTT_TOPIC_ID': user.mqttmetadata.user_topic_id,
                'MQTT_HOST': config.host.HOST_DOCKER_INTERNAL_IP,
                'MQTT_PORT': config.mosquitto.MOSQUITTO_PORT_DOCKER,
                'MQTT_USERNAME': nodered_mqtt_username,
                'MQTT_PASSWORD': nodered_mqtt_password,
            }

            try:
                self.container = self.docker_client.containers.run(
                    'custom-node-red',
                    detach=True,
                    restart_policy={'Name': 'unless-stopped'},
                    ports={'1880/tcp': None},  # Node-RED port dynamically assigned by Docker
                    volumes={f'{self.name}-volume': {'bind': '/data', 'mode': 'rw'}},
                    name=self.name,
                    environment=env,
                    network="bridge"  # Attach the container to the default network
                )
                self.determine_port()
            except (docker.errors.ContainerError, docker.errors.ImageNotFound) as e:
                print(e)  # TODO: Log Error
                self.container = None

    def stop(self):
        if self.container:
            self.determine_port()
            self.container.stop()

    def restart(self):
        if self.container:
            self.container.restart()
            self.determine_port()

    def delete_container(self):
        if self.container:
            self.determine_port()
            try:
                self.container.stop()
                self.container.remove()
                print(f'Container {self.name} has been deleted.')
            except docker.errors.NotFound:
                print(f'Container {self.name} not found.')
            except Exception as e:
                print(f'An error occurred while trying to delete the nodered container: {e}')

    # Deprecated
    def copy_json_to_container(self, container, src_path, dest_path):
        # Create a tar archive of the file
        import tarfile
        from io import BytesIO
        stream = BytesIO()
        with tarfile.open(fileobj=stream, mode='w') as tar:
            tar.add(src_path, arcname=os.path.basename(dest_path))

        # Move the stream's pointer to the beginning
        stream.seek(0)
        container.put_archive(path=os.path.dirname(dest_path), data=stream)

    def update_flows(self, token, flows_json):
        url = f"http://localhost:{self.port}/flows"
        headers = {
            'Authorization': f"Bearer {token}",
            'Content-Type': 'application/json'
        }
        response = requests.post(url, headers=headers, data=flows_json)
        response.raise_for_status()

    def configure_nodered(self, user):
        '''Open flows.json template, replace placeholders for various values and copy it to the container'''

        file_path = os.path.join(os.path.dirname(__file__), 'nodered_flows', 'flows.template.json')
        with open(file_path, 'r') as file:
            flows_json = file.read()

        modified_flows_json = flows_json.replace("MQTT_TOPIC_ID", user.mqttmetadata.user_topic_id)

        nodered_mqtt_inout_username = "Ask the admin how to use the inout topic"  # Placeholder, should be set on devices page
        nodered_mqtt_inout_password = ""  # Placeholder, should be set on devices page
        modified_flows_json = modified_flows_json.replace("MQTT_INOUT_USERNAME", nodered_mqtt_inout_username)
        modified_flows_json = modified_flows_json.replace("MQTT_INOUT_PASSWORD", nodered_mqtt_inout_password)

        # Commented out replacements below are now handled by environmental variables in the Dockerfile

        # modified_flows_json = modified_flows_json.replace("user_bucket_name", user.influxuserdata.bucket_name)

        # # broker_port = "8883" if config.host.TLS == "true" else "1883"
        # broker_port = "1885"  # "1885" if config.host.TLS == "true" else "1884"
        # modified_flows_json = modified_flows_json.replace("broker_port", broker_port)
        # # if config.host.TLS == "true":
        # #     modified_flows_json = modified_flows_json.replace('"usetls": false', '"usetls": true')

        # # host_address = config.host.DOMAIN if config.host.TLS == "true" and config.host.DOMAIN else config.host.IP
        # host_address = "172.17.0.1"
        # modified_flows_json = modified_flows_json.replace("server_ip_or_domain", host_address)
        # modified_flows_json = modified_flows_json.replace("influxdb-org-name", config.influxdb.INFLUX_ORG_NAME)

        # # server_scheme = "https" if config.host.TLS == "true" else "http"
        # # influxdb_port = "8087"  # TODO: NGINX conf is 8087 to reverse proxy 8086. config.influxdb.INFLUX_PORT is 8086
        # server_scheme = "http"
        # influxdb_port = "8086"  # get from config
        # influxdb_url = f"{server_scheme}://{host_address}:{influxdb_port}"
        # modified_flows_json = modified_flows_json.replace("influxdb-url", influxdb_url)

        self.determine_port()

        # Alternative for basic auth with username + password
        # nodered_username = user.nodereduserdata.username
        # nodered_password = user.nodereduserdata.password

        # Generate a JWT token locally (expires in 300 minutes)
        exp = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(minutes=300)
        payload = {
            'username': user.nodereduserdata.username,
            'exp': exp
        }
        token = jwt.encode(payload, self.nodered_data.access_token, algorithm='HS256')
        logger.info(f"Generated JWT token for Node-RED configuration: {token}")
        self.update_flows(token, modified_flows_json)

        self.nodered_data.is_configured = True
        self.nodered_data.save()

    def determine_state(self):
        if self.container:
            self.container.reload()
            container_status = self.container.status
            try:
                container_health = self.container.attrs['State']['Health']['Status']
            except KeyError:
                container_health = 'N/A'
            # Determine the current state based on status and health
            if container_status == 'running' and container_health == 'starting':
                self.state = 'starting'
            elif container_status == 'running' and container_health == 'healthy':
                self.state = 'running'
            elif container_status == 'exited' and container_health == 'unhealthy':
                self.state = 'stopped'
            else:
                self.state = 'unavailable'

        return self.state

    def determine_port(self):
        try:
            if self.container:
                self.container.reload()
                self.port = self.container.attrs['NetworkSettings']['Ports']['1880/tcp'][0]['HostPort']
        except KeyError:
            self.port = None  # TODO: delete this comment if working, else revert: was ''


def update_nodered_nginx_conf(nodered_user_data):
    print('update_nodered_nginx_conf() ausgeführt')  # TODO: Später entfernen bzw durch log ersetzen
    # Logic to update Nginx configuration
    container_name = nodered_user_data.container_name
    port = nodered_user_data.container_port
    if not container_name and port:
        return

    # Path to the server block create script
    # Could be replaced by a python script
    script_path = config.nodered.SERVERBLOCK_CREATE_SCRIPT_PATH

    # Call the script with sudo
    command = ['sudo', script_path, container_name, str(port)]
    result = subprocess.run(
        command,
        check=False,  # change to False to handle errors manually
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        logger.error('Error:', result.stderr.decode())


def del_nodered_nginx_conf(nodered_user_data):
    """
    Run this function when django user is deleted or if
    delete container is implemented on the nodered dashboard page
    """
    container_name = nodered_user_data.container_name

    # Path to the server block create script.
    # Could be replaced by a python script
    script_path = "/etc/nginx/conf.d/nodered_locations"  # config.nodered.SERVERBLOCK_CREATE_SCRIPT_PATH
    config_file_path = os.path.join(script_path, f"{container_name}.conf")

    command = ['sudo', 'rm', config_file_path]
    result = subprocess.run(
        command,
        check=False,  # change to False to handle errors manually
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    server_utils.reload_nginx()

    if result.returncode != 0:
        print('Error:', result.stderr.decode())  # TODO: Später entfernen bzw durch log ersetzen
