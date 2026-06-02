"""
OBI board interface via pylibiio serial backend.
Auto-detects the board on any COM port by scanning for the OBI description.
"""

import iio
import serial.tools.list_ports

OBI_SERIAL_DESC = "USB Serial Port"
OBI_BAUD = 230400
OBI_HW_NAME = "On-Body Injector Development Platform"


def find_obi_uri() -> str | None:
    """Scan COM ports and return the first IIO URI that connects to the OBI board."""
    ports = serial.tools.list_ports.comports()
    for port in sorted(ports, key=lambda p: p.device):
        uri = f"serial:{port.device},{OBI_BAUD},8n1n"
        try:
            ctx = iio.Context(uri)
            hw = ctx.attrs.get("hw_name", "")
            if OBI_HW_NAME.lower() in hw.lower():
                return uri
        except Exception:
            continue
    return None


class OBIBoard:
    def __init__(self, uri: str | None = None):
        if uri is None:
            uri = find_obi_uri()
        if uri is None:
            raise RuntimeError("OBI board not found. Check USB connection.")
        self.uri = uri
        self.ctx = iio.Context(uri)

    # ------------------------------------------------------------------ #
    # Context info
    # ------------------------------------------------------------------ #
    def get_context_info(self) -> dict:
        return {
            "uri": self.uri,
            "description": self.ctx.description,
            "attrs": {k: self.ctx.attrs[k].value for k in self.ctx.attrs},
            "device_count": len(self.ctx.devices),
        }

    # ------------------------------------------------------------------ #
    # Device list
    # ------------------------------------------------------------------ #
    def list_devices(self) -> list[dict]:
        result = []
        for dev in self.ctx.devices:
            result.append({
                "id": dev.id,
                "name": dev.name,
                "channel_count": len(dev.channels),
                "attr_count": len(dev.attrs),
            })
        return result

    def _get_device(self, name_or_id: str):
        for dev in self.ctx.devices:
            if dev.name == name_or_id or dev.id == name_or_id:
                return dev
        raise ValueError(f"Device not found: {name_or_id}")

    # ------------------------------------------------------------------ #
    # Device attributes
    # ------------------------------------------------------------------ #
    def read_device_attr(self, device: str, attr: str) -> str:
        dev = self._get_device(device)
        if attr not in dev.attrs:
            raise ValueError(f"Attribute '{attr}' not found on {device}")
        return dev.attrs[attr].value

    def write_device_attr(self, device: str, attr: str, value: str) -> str:
        dev = self._get_device(device)
        if attr not in dev.attrs:
            raise ValueError(f"Attribute '{attr}' not found on {device}")
        dev.attrs[attr].value = value
        return dev.attrs[attr].value

    def list_device_attrs(self, device: str) -> dict:
        dev = self._get_device(device)
        result = {}
        for name, attr in dev.attrs.items():
            try:
                result[name] = attr.value
            except Exception as e:
                result[name] = f"<error: {e}>"
        return result

    # ------------------------------------------------------------------ #
    # Channel attributes
    # ------------------------------------------------------------------ #
    def list_channels(self, device: str) -> list[dict]:
        dev = self._get_device(device)
        return [
            {
                "id": ch.id,
                "name": ch.name,
                "type": str(ch.type),
                "output": ch.output,
                "attr_count": len(ch.attrs),
            }
            for ch in dev.channels
        ]

    def read_channel_attr(self, device: str, channel: str, attr: str) -> str:
        dev = self._get_device(device)
        ch = None
        for c in dev.channels:
            if c.id == channel or c.name == channel:
                ch = c
                break
        if ch is None:
            raise ValueError(f"Channel '{channel}' not found on {device}")
        if attr not in ch.attrs:
            raise ValueError(f"Attribute '{attr}' not found on channel {channel}")
        return ch.attrs[attr].value

    def write_channel_attr(self, device: str, channel: str, attr: str, value: str) -> str:
        dev = self._get_device(device)
        ch = None
        for c in dev.channels:
            if c.id == channel or c.name == channel:
                ch = c
                break
        if ch is None:
            raise ValueError(f"Channel '{channel}' not found on {device}")
        if attr not in ch.attrs:
            raise ValueError(f"Attribute '{attr}' not found on channel {channel}")
        ch.attrs[attr].value = value
        return ch.attrs[attr].value

    def list_channel_attrs(self, device: str, channel: str) -> dict:
        dev = self._get_device(device)
        ch = None
        for c in dev.channels:
            if c.id == channel or c.name == channel:
                ch = c
                break
        if ch is None:
            raise ValueError(f"Channel '{channel}' not found on {device}")
        result = {}
        for name, attr in ch.attrs.items():
            try:
                result[name] = attr.value
            except Exception as e:
                result[name] = f"<error: {e}>"
        return result

    # ------------------------------------------------------------------ #
    # Debug attributes
    # ------------------------------------------------------------------ #
    def read_debug_attr(self, device: str, attr: str) -> str:
        dev = self._get_device(device)
        if attr not in dev.debug_attrs:
            raise ValueError(f"Debug attribute '{attr}' not found on {device}")
        return dev.debug_attrs[attr].value

    def write_debug_attr(self, device: str, attr: str, value: str) -> str:
        dev = self._get_device(device)
        if attr not in dev.debug_attrs:
            raise ValueError(f"Debug attribute '{attr}' not found on {device}")
        dev.debug_attrs[attr].value = value
        return dev.debug_attrs[attr].value
