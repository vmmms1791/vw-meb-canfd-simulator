#!/usr/bin/env python3
"""
Tests for analyzer module
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import sys
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from analyzer import AnalyzerApp, ISO15765Decoder


class TestISO15765Decoder:
    """Test ISO-TP (ISO 15765-2) decoder."""

    def test_single_frame(self):
        decoder = ISO15765Decoder()
        frame = {
            "can_id": 0x17FE007B,
            "data": bytes([0x03, 0x62, 0x01, 0x04, 0x03, 0xE8]),  # SF: len=3, 0x62 0x0104 0x03E8
            "timestamp_us": 1000000,
        }
        result = decoder.feed_frame(frame)
        assert result is not None
        assert result["type"] == "single"
        assert result["service"] == 0x62
        assert result["payload"] == bytes([0x62, 0x01, 0x04, 0x03, 0xE8])

    def test_first_frame(self):
        decoder = ISO15765Decoder()
        # First frame: 20 bytes payload
        frame = {
            "can_id": 0x17FE007B,
            "data": bytes([0x10, 0x14] + [0x62, 0x01, 0x04] + [0x00]*13),  # FF: len=20, payload start
            "timestamp_us": 1000000,
        }
        result = decoder.feed_frame(frame)
        assert result is None  # First frame doesn't return complete message
        assert 0x17FE007B in decoder.sessions

    def test_consecutive_frames(self):
        decoder = ISO15765Decoder()
        # First frame
        ff = {
            "can_id": 0x17FE007B,
            "data": bytes([0x10, 0x0A, 0x62, 0x01, 0x04, 0x03, 0xE8, 0x00]),  # FF: len=10
            "timestamp_us": 1000000,
        }
        decoder.feed_frame(ff)

        # Consecutive frame
        cf = {
            "can_id": 0x17FE007B,
            "data": bytes([0x21, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00]),  # CF sn=1
            "timestamp_us": 1001000,
        }
        result = decoder.feed_frame(cf)
        assert result is not None
        assert result["type"] == "reassembled"
        assert len(result["payload"]) == 10


class TestAnalyzerApp:
    """Test analyzer application."""

    def test_load_csv(self):
        """Test loading CSV capture."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            f.write("timestamp_us,direction,can_id_hex,dlc,data_hex,flags,extended,fd\n")
            f.write("1000000,RX,5A2,8,0102030405060708,0x00,0,0\n")
            f.write("1000001,RX,17FC007B,8,0222010400000000,0x00,1,0\n")
            f.write("1000002,RX,17FE007B,8,0662010403E80000,0x00,1,0\n")
            temp_path = f.name

        args = Mock()
        args.input = temp_path
        args.filter = None
        args.decode_uds = False
        args.dbc = None
        args.stats = False
        args.output = None

        app = AnalyzerApp(args)
        app._load_capture()

        assert app.stats["total_frames"] == 3
        assert app.stats["extended_frames"] == 2
        assert app.stats["standard_frames"] == 1
        assert 0x5A2 in app.stats["id_counter"]
        assert 0x17FC007B in app.stats["id_counter"]

        Path(temp_path).unlink()

    def test_load_jsonl(self):
        """Test loading JSONL capture."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write(json.dumps({"timestamp_us": 1000000, "direction": "RX", "can_id": 0x5A2, "can_id_hex": "5A2", "dlc": 8, "data": [1,2,3,4,5,6,7,8], "data_hex": "0102030405060708", "flags": 0, "extended": False, "fd": False}) + "\n")
            temp_path = f.name

        args = Mock()
        args.input = temp_path
        args.filter = None
        args.decode_uds = False
        args.dbc = None
        args.stats = False
        args.output = None

        app = AnalyzerApp(args)
        app._load_capture()

        assert app.stats["total_frames"] == 1

        Path(temp_path).unlink()

    def test_filter_application(self):
        """Test ID filtering."""
        app = AnalyzerApp(Mock())
        app.frames = [
            {"can_id": 0x5A2, "data": b"", "timestamp_us": 1},
            {"can_id": 0x17FC007B, "data": b"", "timestamp_us": 2},
            {"can_id": 0x3B5, "data": b"", "timestamp_us": 3},
        ]
        app.stats["total_frames"] = 3
        app.stats["id_counter"] = {0x5A2: 1, 0x17FC007B: 1, 0x3B5: 1}

        app.filter_ids = {0x5A2, 0x3B5}
        app._apply_filter()

        assert app.stats["filtered_frames"] == 2
        assert len(app.frames) == 2
        assert all(f["can_id"] in {0x5A2, 0x3B5} for f in app.frames)

    def test_sid_name_mapping(self):
        """Test UDS service ID to name mapping."""
        app = AnalyzerApp(Mock())
        assert app._sid_name(0x10) == "SessionControl"
        assert app._sid_name(0x50) == "SessionControl+"
        assert app._sid_name(0x22) == "ReadDID"
        assert app._sid_name(0x62) == "ReadDID+"
        assert app._sid_name(0x7F) == "NegResponse"
        assert app._sid_name(0x99) == "0x99"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])