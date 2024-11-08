import pytest
from datetime import datetime
from unittest.mock import Mock, patch
from loguru import logger
from h3xrecon.core.database import DatabaseManager
from h3xrecon.core.config import Config

pytestmark = pytest.mark.asyncio

class TestDatabaseManager:
    @pytest.fixture
    def mock_config(self):
        """Mock configuration for testing"""
        config = Mock()
        config.database = Mock()
        config.database.to_dict.return_value = {
            'host': 'test_host',
            'port': 5432,
            'user': 'test_user',
            'password': 'test_password',
            'database': 'test_db'
        }
        return config

    @pytest.fixture
    def db_manager(self, mock_config):
        """Fixture to create a DatabaseManager instance"""
        return DatabaseManager(mock_config)

    class MockRecord(dict):
        """Mock class to simulate asyncpg Record objects"""
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.items = self.items

    async def test_format_records_with_datetime(self, db_manager):
        """Test formatting records with datetime objects"""
        test_date = datetime(2024, 1, 1, 12, 0, 0)
        mock_records = [
            self.MockRecord({
                'id': 1,
                'name': 'test.com',
                'discovered_at': test_date
            }),
            self.MockRecord({
                'id': 2,
                'name': 'example.com',
                'discovered_at': test_date
            })
        ]

        result = await db_manager.format_records(mock_records)

        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]['id'] == 1
        assert result[0]['name'] == 'test.com'
        assert result[0]['discovered_at'] == test_date.isoformat()

    async def test_format_records_without_datetime(self, db_manager):
        """Test formatting records without datetime objects"""
        mock_records = [
            self.MockRecord({
                'id': 1,
                'name': 'test.com',
                'count': 42
            })
        ]

        result = await db_manager.format_records(mock_records)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['id'] == 1
        assert result[0]['name'] == 'test.com'
        assert result[0]['count'] == 42

    async def test_format_records_empty_list(self, db_manager):
        """Test formatting empty list of records"""
        result = await db_manager.format_records([])
        
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_format_records_error_handling(self, db_manager):
        """Test error handling in format_records"""
        # Create a mock record that will definitely raise an exception
        class BadObject:
            def items(self):
                raise Exception("Forced error for testing")
        
        mock_records = [BadObject()]  # This will raise an exception when items() is called

        result = await db_manager.format_records(mock_records)
        
        # Should return empty list on error
        assert isinstance(result, list)
        assert len(result) == 0

    async def test_format_records_with_none_values(self, db_manager):
        """Test formatting records with None values"""
        mock_records = [
            self.MockRecord({
                'id': 1,
                'name': None,
                'timestamp': None
            })
        ]

        result = await db_manager.format_records(mock_records)

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]['id'] == 1
        assert result[0]['name'] is None
        assert result[0]['timestamp'] is None
