from .setup_utils import run_bash, log, get_setup_dir, get_conf_path

SECURITY_INSTALL_LOG_FILE_NAME = 'install_02_security_packages.log'


def install_security_packages(setup_scheme):
	setup_dir = get_setup_dir()
	config_path = get_conf_path()

	mqtt_port = 1883
	if setup_scheme != 'NO_TLS':
		mqtt_port = 8883

	commands = [
		# Install ufw
		'apt install -y ufw',
		# Configure ufw
		'ufw allow ssh',
		'ufw allow 80/tcp',  # for http
		'ufw allow 443/tcp',  # for https
		f'ufw allow {mqtt_port}/tcp',  # For MQTT
		# 'sudo ufw allow 8087/tcp',  # InfluxDB
		'sudo ufw allow in from 172.17.0.0/16 to any port 8086',  # InfluxDB access in docker network
		'sudo ufw allow in from 172.17.0.0/16 to any port 1884',  # Mosquitto access in docker network
		'sudo ufw allow in from 172.17.0.0/16 to any port 1885',  # Mosquitto access in docker network
		# Block inter-container communication comes after docker installation 
		# Allow traffic from containers to host 
		# Allow traffic from host to containers
		# TODO: avoid opening the InfluxDB port by implementing docker network to allow influxdb node connect directly to the db
		# 'ufw allow 3000/tcp',  # For Grafana admin to login to dashboard. If used with TLS, add proxy pass to nginx!
		'echo',
		"echo 'To enable ufw firewall, automatic response to confirmation will be provided.'",
		"echo 'y' | sudo ufw enable",  # This sends "y" as input to the ufw enable command
		'sudo ufw status',
		# Install fail2ban
		'apt install -y fail2ban',
		'systemctl start fail2ban',
		'systemctl enable fail2ban',
		# Configure fail2ban
		f'bash {config_path}/tmp.jail.local.sh > {setup_dir}/setup_files/tmp/jail.local',
		f'cp {setup_dir}/setup_files/tmp/jail.local /etc/fail2ban/jail.local',
		# Restart fail2ban to apply any changes
		'systemctl restart fail2ban',
	]
	for command in commands:
		output = run_bash(command)
		log(output, SECURITY_INSTALL_LOG_FILE_NAME)

	log('Security packages installed', SECURITY_INSTALL_LOG_FILE_NAME)
