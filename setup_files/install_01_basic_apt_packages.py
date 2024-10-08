from .setup_utils import run_bash, log

APT_INSTALL_LOG_FILE_NAME = 'install_01_basic_apt_packages.log'


def install_basic_apt_packages():
	commands = [
		'apt update',
		'apt install -y python3-pip python3-venv python3-dev',
		# adduser is requirement of PostgreSQL
		'apt install -y curl wget inotify-tools zip adduser git',
		# libfontconfig1 is requirement of Grafana
		'apt install -y libopenjp2-7 libtiff6 libfontconfig1',
	]
	for command in commands:
		output = run_bash(command)
		log(output, APT_INSTALL_LOG_FILE_NAME)

	log('Basic APT packages installed', APT_INSTALL_LOG_FILE_NAME)
