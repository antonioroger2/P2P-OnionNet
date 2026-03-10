import streamlit as st
import os
import atexit
import signal
import subprocess
import time
from core.overlay import OnionNode
from ui.dashboard import render_dashboard

ONIONNET_PORTS = list(range(6000, 6011)) + [8080]

os.makedirs("data/received", exist_ok=True)
os.makedirs("data/shared", exist_ok=True)
os.makedirs("data/torrents", exist_ok=True)

st.set_page_config(
    page_title="OnionNet P2P",
    page_icon="🧅",
    layout="wide",
    initial_sidebar_state="expanded"
)


def _cleanup_node(*_args):
    node = st.session_state.get('node')
    if node:
        node.shutdown()
    _kill_listeners_on_ports(ONIONNET_PORTS)


def _kill_listeners_on_ports(ports):
    current_pid = os.getpid()
    pids = set()

    for port in ports:
        try:
            res = subprocess.run(
                ["lsof", "-ti", f"TCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                check=False,
            )
            for raw in res.stdout.splitlines():
                raw = raw.strip()
                if not raw:
                    continue
                pid = int(raw)
                if pid != current_pid:
                    pids.add(pid)
        except Exception:
            continue

    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass

    time.sleep(0.3)

    for pid in pids:
        try:
            os.kill(pid, 0)
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass


def _startup_port_sweep():
    if st.session_state.get('_startup_port_sweep_done'):
        return
    _kill_listeners_on_ports(ONIONNET_PORTS)
    st.session_state._startup_port_sweep_done = True


_startup_port_sweep()

if 'node' not in st.session_state:
    st.session_state.node = OnionNode(bind_ip='0.0.0.0')


if '_cleanup_registered' not in st.session_state:
    atexit.register(_cleanup_node)
    try:
        signal.signal(signal.SIGINT, _cleanup_node)
        signal.signal(signal.SIGTERM, _cleanup_node)
    except ValueError:
        # Streamlit may execute this script in a non-main thread.
        pass
    st.session_state._cleanup_registered = True

render_dashboard(st.session_state.node)