from .setup_utils import run_bash, log

GRAFANA_INSTALL_LOG_FILE_NAME = "install_06_grafana.log"


def install_grafana(arch):
    """
    TODO: Implement Grafana setup
    """

    commands = [f'echo "Grafana installation not yet implemented. arch: {arch}"']

    for command in commands:
        output = run_bash(command)
        log(output, GRAFANA_INSTALL_LOG_FILE_NAME)

    config_data = {
        "GRAFANA_HOST": "localhost",
        "GRAFANA_PORT": 3000,
        "GRAFANA_ORG_NAME": "iotree42",
    }
    log("Grafana installation done", GRAFANA_INSTALL_LOG_FILE_NAME)
    return config_data
