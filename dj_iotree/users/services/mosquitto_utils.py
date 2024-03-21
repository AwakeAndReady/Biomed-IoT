from users.models import MqttMetaData, MqttClient
from .mosquitto_dynsec import MosquittoDynSec as dynsec
from django.db import transaction
from django.db import IntegrityError
import secrets
from django.contrib import messages
from enum import Enum, unique


class MqttMetaDataManager():
    """
    Manages MQTT metadata for users.

    This class is responsible for creating and managing MQTT user metadata,
    including unique topic IDs and roles for Node-RED and device communication.
    It should be used during user registration to initialize MQTT metadata.
    """
    def __init__(self, user):
        self.user = user
        self.metadata = self._get_or_create_mqtt_meta_data()

    def _get_or_create_mqtt_meta_data(self):
        """
        Returns the MqttMetaData instance for the current user, 
        creating it if it does not exist.
        """
        meta_data = None
        with transaction.atomic():
            try:
                user_topic_id, nodered_role_name, device_role_name = MqttMetaData.generate_unique_mqtt_metadata()
                meta_data, created = MqttMetaData.objects.get_or_create(
                    user=self.user,
                    defaults={
                        'user_topic_id': user_topic_id,
                        'nodered_role_name': nodered_role_name,
                        'device_role_name': device_role_name
                    }
                )
            except IntegrityError:
                print("Integrity-Error while trying to create MqttMetaData. Check if MqttMetaData already exists")

        return meta_data
    
    def create_nodered_role(self):
        """
        Creates the Node-RED role based on the user's MQTT metadata.
        Returns True if the role creation was successful, False otherwise.
        """
        success = False
        if self.metadata != None:
            nodered_sub_topic = f"in/{self.metadata.user_topic_id}/#"
            nodered_pub_topic = f"out/{self.metadata.user_topic_id}/#"

            success, _, _ = dynsec.create_role(self.metadata.nodered_role_name, 
                                            acls=[{"acltype": "subscribePattern", "topic": nodered_sub_topic, "priority": -1, "allow": True}, 
                                                  {"acltype": "publishClientSend", "topic": nodered_pub_topic, "priority": -1, "allow": True}
                                                ])
        return success

    def create_device_role(self):
        """
        Creates a device role based on the user's MQTT metadata.
        Returns True if the role creation was successful, False otherwise.
        """
        success = False
        if self.metadata != None:
            device_sub_topic = f"out/{self.metadata.user_topic_id}/#"
            device_pub_topic = f"in/{self.metadata.user_topic_id}/#"

            success, _ = dynsec.create_role(self.metadata.device_role_name, 
                                            acls=[{"acltype": "subscribePattern", "topic": device_sub_topic, "priority": -1, "allow": True}, 
                                                  {"acltype": "publishClientSend", "topic": device_pub_topic, "priority": -1, "allow": True}
                                                ])
        return success

    def delete_nodered_role(self):
        """
        Deletes the Node-RED role based on the nodered_role_name in the user's MQTT metadata.
        Returns True if the role deletion was successful, False otherwise.
        """
        success = False
        if self.metadata != None:
            nodered_role_name = self.metadata.nodered_role_name
            success, _ = dynsec.delete_role(nodered_role_name)
        return success

    def delete_device_role(self):
        """
        Deletes a device role based on the device_role_name in the user's MQTT metadata.
        Returns True if the role deletion was successful, False otherwise.
        """
        success = False
        if self.metadata != None:
            device_role_name = self.metadata.device_role_name
            success, _ = dynsec.delete_role(device_role_name)
        return success


@unique
class RoleType(Enum):
    """ 
    Used for MqttClientManager.create_client(self, textname="New MQTT Device", role_type=None).
    Prevents the use of 'magic values'.
    """
    DEVICE = "device"
    NODERED = "nodered"


class MqttClientManager():
    """
    Requires MqttMetaData already to be set.
    """
    def __init__(self, user):
        self.user = user

    def create_client(self, textname="New MQTT Device", role_type=None):
        # Generate a unique username and password for the MQTT client
        new_username = MqttClient.generate_unique_username()
        new_password = MqttClient.generate_password()

        # Retrieve the MQTT meta data for the user to get the device role name
        try:
            mqtt_meta_data = MqttMetaData.objects.get(user=self.user)
            if role_type == "device":
                rolename = mqtt_meta_data.device_role_name
            elif role_type == "nodered":
                rolename = mqtt_meta_data.nodered_role_name

            # Create the MQTT client in the mosquitto dynamic security plugin
            success, _ = dynsec.create_client(new_username, new_password, textname, rolename)

            if success:
                # If the MQTT client was successfully created in the dynsec system, save it to the database
                MqttClient.objects.create(
                    user=self.user,
                    username=new_username,
                    password=new_password,
                    textname=textname,
                    rolename=rolename
                )
                print(f"MQTT client {new_username} created successfully.")
            else:
                print("Failed to create MQTT client in dynamic security system.")
        except MqttMetaData.DoesNotExist:
            print("MqttMetaData does not exist for the user.")
        except IntegrityError as e:
            print(f"Database error when creating MQTT client: {e}")

    def modify_client(self, client_username, textname="New MQTT Device"):
        """
        Modifies the textname of an existing MQTT client in both the database and the dynamic security system,
        ensuring that changes are only committed to the database after successful modification in the dynamic security system.
        """
        try:
            # Attempt to find the MQTT client in the database
            mqtt_client = MqttClient.objects.get(username=client_username, user=self.user)

            # Next, attempt to modify the client in the dynamic security system
            success, _ = dynsec.modify_client(client_username, textname=textname)
            if success:
                # If modification in the dynamic security system is successful, update the database
                mqtt_client.textname = textname
                mqtt_client.save()
                print(f"MQTT client {client_username}'s textname updated to '{textname}' successfully.")
            else:
                print(f"Failed to modify MQTT client {client_username} in dynamic security system.")
        except MqttClient.DoesNotExist:
            print(f"MQTT client {client_username} not found for the user.")


    def delete_client(self, client_username):
        """
        Deletes an MQTT client from both the database and the dynamic security system.
        """
        try:
            mqtt_client = MqttClient.objects.get(username=client_username, user=self.user)

            # Attempt to delete the client from the dynamic security system
            success = dynsec.delete_client(client_username)

            if success:
                mqtt_client.delete()
                print(f"MQTT client {client_username} deleted successfully.")
            else:
                print(f"Failed to delete MQTT client {client_username} from dynamic security system.")
        except MqttClient.DoesNotExist:
            print(f"MQTT client {client_username} not found for the user.")

    def get_device_clients(self):
        """
        Retrieves a list of MQTT device clients associated with the user's device role.
        """
        try:
            mqtt_meta_data = MqttMetaData.objects.get(user=self.user)
            device_role_name = mqtt_meta_data.device_role_name
            # Filter the clients based on the users 'device_role_name'
            clients = MqttClient.objects.filter(user=self.user, rolename=device_role_name)
            return clients
        except MqttMetaData.DoesNotExist:
            print("MqttMetaData not found for the user.")
            return []


    def get_nodered_client(self):
        """
        Retrieves the MQTT Node-RED client associated with the user's nodered role.
        """
        try:
            mqtt_meta_data = MqttMetaData.objects.get(user=self.user)
            nodered_role_name = mqtt_meta_data.nodered_role_name
            # Filter the clients based on the users 'nodered_role_name'
            client = MqttClient.objects.filter(user=self.user, rolename=nodered_role_name).first()
            return client
        except MqttMetaData.DoesNotExist:
            print("MqttMetaData not found for the user.")
            return None