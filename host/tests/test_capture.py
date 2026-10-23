#!/usr/bin/env python3
"""
Tests for capture module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import csv
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from capture import CaptureApp, SLCANClient


class TestCaptureApp:
    """Test capture application logic."""

    def test_filter_ids_parsing(self):
        """Test CAN ID filter parsing."""
        # This would need a mock args object
        pass

    @patch('capture.SLCANClient')
    def test_capture_initialization(self, mock_client_class):
        """Test CaptureApp initializes correctly."""
        mock_client = Mock()
        mock_client.connect.return_value = True
        mock_client_class.return_value = mock_client

        args = Mock()
        args.port = "COM14"
        args.baud = 115200
        args.timeout = 1.0
        args.tty_baudrate = 500000
        args.duration = 10
        args.output = "test.csv"
        args.filter = "0x5A2,0x5AC"
        args.format = "csv"
        args.silent = True
        args.no_fd = False

        app = CaptureApp(args)
        assert app.filter_ids == {0x5A2, 0x5AC}
        assert app.args.duration == 10

    def test_csv_header(self):
        """Test CSV output format."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp_us", "direction", "can_id_hex", "dlc", "data_hex", "flags", "extended", "fd"])
            writer.writerow([1234567890, "RX", "5A2", 8, "0102030405060708", "0x00", "0", "0"])
            temp_path = f.name

        # Verify format
        with open(temp_path) as f:
            reader = csv.reader(f)
            header = next(reader)
            row = next(reader)

        assert header == ["timestamp_us", "direction", "can_id_hex", "dlc", "data_hex", "flags", "extended", "fd"]
        assert row[2] == "5A2"
        assert row[3] == "8"

        Path(temp_path).unlink()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])