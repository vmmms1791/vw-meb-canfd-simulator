#!/usr/bin/env python3
"""
Tests for SLCAN client
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from capture import SLCANClient


class TestSLCANClient:
    """Test SLCAN frame parsing."""

    def test_parse_standard_frame(self):
        client = SLCANClient("COM1", 115200)
        # Standard frame: t12345678\r
        line = b"t12345678\r"
        result = client._parse_slcan_frame(line)
        assert result is not None
        assert result["can_id"] == 0x123
        assert result["dlc"] == 4
        assert result["data"] == bytes([0x56, 0x78])
        assert not result["extended"]
        assert not result["fd"]

    def test_parse_extended_frame(self):
        client = SLCANClient("COM1", 115200)
        # Extended frame: T12345678812345678\r
        line = b"T12345678812345678\r"
        result = client._parse_slcan_frame(line)
        assert result is not None
        assert result["can_id"] == 0x12345678
        assert result["dlc"] == 8
        assert result["data"] == bytes([0x12, 0x34, 0x56, 0x78])
        assert result["extended"]
        assert not result["fd"]

    def test_parse_fd_extended_frame(self):
        client = SLCANClient("COM1", 115200)
        # FD Extended frame: F1234567881234567800\r
        line = b"F1234567881234567800\r"
        result = client._parse_slcan_frame(line)
        assert result is not None
        assert result["can_id"] == 0x12345678
        assert result["dlc"] == 8
        assert result["data"] == bytes([0x12, 0x34, 0x56, 0x78])
        assert result["extended"]
        assert result["fd"]
        assert result["flags"] == 0x00

    def test_parse_dlc_mapping(self):
        client = SLCANClient("COM1", 115200)
        # Test DLC 9-15 mapping
        test_cases = [
            (9, 12), (10, 16), (11, 20), (12, 24),
            (13, 32), (14, 48), (15, 64)
        ]
        for dlc, expected_len in test_cases:
            dlc_hex = format(dlc, 'X')
            data_hex = "00" * expected_len
            line = f"F12345678{dlc_hex}{data_hex}00\r".encode()
            result = client._parse_slcan_frame(line)
            assert result is not None
            assert result["data_len"] == expected_len, f"DLC {dlc} should map to {expected_len} bytes"

    def test_parse_invalid_frame(self):
        client = SLCANClient("COM1", 115200)
        # Invalid frame
        result = client._parse_slcan_frame(b"INVALID\r")
        assert result is None

    def test_parse_ok_response(self):
        client = SLCANClient("COM1", 115200)
        # OK response
        result = client._parse_slcan_frame(b"\r")
        assert result is None

    def test_parse_bell_response(self):
        client = SLCANClient("COM1", 115200)
        # Bell (error) response
        result = client._parse_slcan_frame(b"\a")
        assert result is None

    def test_parse_timestamp(self):
        client = SLCANClient("COM1", 115200)
        # Timestamp
        result = client._parse_slcan_frame(b"~1234\r")
        assert result is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])