import subprocess
import time
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

class K8sPortForwarder:
    """
    Manages background kubectl port-forward processes to expose
    ports (e.g. 8000 for Django backend, 3000 for Frontend) from
    the isolated Kubernetes Pod to localhost.
    """

    def __init__(self, pod_name: str, namespace: str = "default"):
        self.pod_name = pod_name
        self.namespace = namespace
        self.process: Optional[subprocess.Popen] = None

    def start(self, port_mappings: List[str] = None):
        """
        Starts port forwarding in the background.
        port_mappings: e.g. ["8000:8000", "3000:3000"]
        """
        if port_mappings is None:
            port_mappings = ["8000:8000", "3000:3000"]

        cmd = [
            "kubectl", "port-forward",
            f"pod/{self.pod_name}",
            f"--namespace={self.namespace}",
            "--address=0.0.0.0"
        ] + port_mappings

        logger.info(f"[PortForwarder] Starting port forward for {self.pod_name}: {port_mappings}")
        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        time.sleep(1.5)  # Allow port forward tunnel to bind

        if self.process.poll() is not None:
            err = self.process.stderr.read()
            logger.error(f"[PortForwarder] Failed to bind ports: {err}")
            return False

        logger.info(f"[PortForwarder] Ports forwarded successfully to localhost: {port_mappings}")
        return True

    def stop(self):
        """
        Terminates the port-forwarding tunnel.
        """
        if self.process and self.process.poll() is None:
            logger.info(f"[PortForwarder] Stopping port forward for {self.pod_name}")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except Exception:
                self.process.kill()
