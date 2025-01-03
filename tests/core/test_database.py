import pytest
from unittest.mock import AsyncMock
from h3xrecon.core import DatabaseManager
from h3xrecon.core.database import DbResult

@pytest.fixture
async def mock_pool():
    """Fixture to provide a mocked database pool"""
    pool = AsyncMock()
    
    # Mock connection context manager
    conn = AsyncMock()
    pool.acquire.return_value.__aenter__.return_value = conn
    
    # Mock fetch methods
    conn.fetch.return_value = [{'id': 1, 'inserted': True}]
    conn.fetchrow.return_value = {'id': 1, 'ip': '192.168.1.1', 'ptr': 'test.example.com', 'program_id': 1}
    
    return pool

@pytest.fixture
async def db_manager():
    """Fixture to provide a database manager instance with mocked pool"""
    manager = DatabaseManager()
    # Mock the connect method to prevent actual database connection
    manager.connect = AsyncMock()
    manager.pool = AsyncMock()
    manager.ensure_connected = AsyncMock()
    manager.close = AsyncMock()
    return manager

@pytest.mark.asyncio
class TestDatabaseManager:
    
    async def test_insert_ip_valid_new(self, db_manager):
        """Test inserting a new valid IP address"""
        ip = "192.168.1.1"
        ptr = "test.example.com"
        program_id = 1
        
        # Configure mock to simulate new insertion (xmax = 0)
        mock_result = DbResult(success=True, data=[{'id': 1, 'inserted': True}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_ip(ip, ptr, program_id)
        assert result is True  # Should be True for new insertions
        
        db_manager._write_records.assert_called_once()
        call_args = db_manager._write_records.call_args[0]
        assert 'INSERT INTO ips' in call_args[0]
        assert call_args[1:] == (ip, ptr, program_id)

    async def test_insert_ip_valid_update(self, db_manager):
        """Test updating an existing IP address"""
        ip = "192.168.1.1"
        ptr = "test.example.com"
        program_id = 1
        
        # Configure mock to simulate update (xmax != 0)
        mock_result = DbResult(success=True, data=[{'id': 1, 'inserted': False}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_ip(ip, ptr, program_id)
        assert result is False  # Should be False for updates

    async def test_insert_ip_invalid(self, db_manager):
        """Test inserting an invalid IP address"""
        result = await db_manager.insert_ip("invalid.ip", "test.ptr", 1)
        assert result is False

    async def test_insert_ip_database_error(self, db_manager):
        """Test handling of database errors during insertion"""
        ip = "192.168.1.1"
        ptr = "test.example.com"
        program_id = 1

        db_manager._write_records = AsyncMock(return_value=DbResult(success=False, error="Database error"))
        result = await db_manager.insert_ip(ip, ptr, program_id)
        assert result is False

    async def test_insert_ip_empty_result(self, db_manager):
        """Test handling of empty result from database"""
        ip = "192.168.1.1"
        ptr = "test.example.com"
        program_id = 1

        db_manager._write_records = AsyncMock(return_value=DbResult(success=True, data=[]))
        result = await db_manager.insert_ip(ip, ptr, program_id)
        assert result is False

    async def test_insert_ip_ipv6(self, db_manager):
        """Test inserting an IPv6 address"""
        ip = "2001:db8::1"
        ptr = "ipv6.example.com"
        program_id = 1

        mock_result = DbResult(success=True, data=[{'id': 1, 'inserted': True}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_ip(ip, ptr, program_id)
        assert result is True  # Should be True for new insertions
        
        db_manager._write_records.assert_called_once()
        call_args = db_manager._write_records.call_args[0]
        assert 'INSERT INTO ips' in call_args[0]
        assert call_args[1:] == (ip, ptr, program_id)

    async def test_insert_domain_valid_new(self, db_manager):
        """Test inserting a new valid domain"""
        domain = "test.example.com"
        program_id = 1
        ips = ["192.168.1.1"]
        cnames = ["alias.example.com"]
        
        # Mock check_domain_regex_match to return True (domain is in scope)
        db_manager.check_domain_regex_match = AsyncMock(return_value=True)
        
        # Mock _fetch_value for IP lookup
        db_manager._fetch_value = AsyncMock(return_value=DbResult(success=True, data=1))
        
        # Configure mock for domain insertion
        mock_result = DbResult(success=True, data=[{'inserted': True}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_domain(domain, program_id, ips, cnames)
        assert result is True
        
        # Verify _write_records was called with correct parameters
        db_manager._write_records.assert_called_once()
        call_args = db_manager._write_records.call_args[0]
        assert 'INSERT INTO domains' in call_args[0]
        assert call_args[1:] == (domain.lower(), program_id, [1], ['alias.example.com'], False)

    async def test_insert_domain_valid_update(self, db_manager):
        """Test updating an existing domain"""
        domain = "test.example.com"
        program_id = 1
        
        # Configure mock to simulate update (xmax != 0)
        mock_result = DbResult(success=True, data=[{'id': 1, 'inserted': False}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_domain(domain, program_id)
        assert result is False  # Should be False for updates

    async def test_insert_domain_invalid(self, db_manager):
        """Test inserting an invalid domain"""
        # Test with invalid domain format
        result = await db_manager.insert_domain("invalid..domain", 1)
        assert result is False

    async def test_insert_domain_database_error(self, db_manager):
        """Test handling of database errors during domain insertion"""
        domain = "test.example.com"
        program_id = 1

        db_manager._write_records = AsyncMock(return_value=DbResult(success=False, error="Database error"))
        result = await db_manager.insert_domain(domain, program_id)
        assert result is False

    async def test_insert_domain_empty_result(self, db_manager):
        """Test handling of empty result from database"""
        domain = "test.example.com"
        program_id = 1

        db_manager._write_records = AsyncMock(return_value=DbResult(success=True, data=[]))
        result = await db_manager.insert_domain(domain, program_id)
        assert result is False

    async def test_insert_domain_with_wildcard(self, db_manager):
        """Test inserting a domain with wildcard (should fail)"""
        domain = "*.example.com"
        program_id = 1
        
        result = await db_manager.insert_domain(domain, program_id)
        assert result is False

    async def test_insert_domain_with_email(self, db_manager):
        """Test inserting a domain with email format (should fail)"""
        domain = "user@example.com"
        program_id = 1
        
        result = await db_manager.insert_domain(domain, program_id)
        assert result is False

    async def test_insert_url_valid_new(self, db_manager):
        """Test inserting a new valid URL"""
        url = "https://example.com/path"
        program_id = 1
        httpx_data = {
            'url': url,
            'host': 'example.com',
            'path': '/path',
            'port': '443',
            'status_code': '200',
            'content_length': '1000',
            'words': '100',
            'lines': '50',
            'timestamp': '2024-01-01T00:00:00Z'
        }
        
        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        # Configure mock for URL insertion
        mock_result = DbResult(success=True, data=[{'inserted': True}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_url(url, httpx_data, program_id)
        assert result is True
        
        # Verify _write_records was called with correct parameters
        db_manager._write_records.assert_called_once()
        call_args = db_manager._write_records.call_args[0]
        assert 'INSERT INTO urls' in call_args[0]
        assert call_args[1] == url.lower()
        assert call_args[2] == program_id

    async def test_insert_url_valid_update(self, db_manager):
        """Test updating an existing URL"""
        url = "https://example.com/path"
        program_id = 1
        httpx_data = {
            'url': url,
            'host': 'example.com',
            'path': '/path',
            'status_code': '200'
        }
        
        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        # Configure mock to simulate update
        mock_result = DbResult(success=True, data=[{'inserted': False}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_url(url, program_id, httpx_data)
        assert result is False

    async def test_insert_url_database_error(self, db_manager):
        """Test handling of database errors during URL insertion"""
        url = "https://example.com"
        program_id = 1
        httpx_data = {'url': url}
        
        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        db_manager._write_records = AsyncMock(return_value=DbResult(success=False, error="Database error"))
        result = await db_manager.insert_url(url, program_id, httpx_data)
        assert result is False

    async def test_insert_url_empty_result(self, db_manager):
        """Test handling of empty result from database"""
        url = "https://example.com"
        program_id = 1
        httpx_data = {'url': url}
        
        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        db_manager._write_records = AsyncMock(return_value=DbResult(success=True, data=[]))
        result = await db_manager.insert_url(url, program_id, httpx_data)
        assert result is False

    async def test_insert_url_invalid_data(self, db_manager):
        """Test inserting URL with invalid data types"""
        url = "https://example.com"
        program_id = 1
        httpx_data = {
            'url': url,
            'content_length': 'invalid',  # Should be int
            'status_code': 'invalid',     # Should be int
            'timestamp': 'invalid-date'   # Should be valid datetime string
        }
        
        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        # Configure mock for URL insertion
        mock_result = DbResult(success=True, data=[{'inserted': True}])
        db_manager._write_records = AsyncMock(return_value=mock_result)
        
        result = await db_manager.insert_url(url, program_id, httpx_data)
        assert result is False

    async def test_insert_url_invalid_format(self, db_manager):
        """Test inserting URLs with invalid formats"""
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",  # not http/https
            "http://",  # no domain
            "https://invalid..domain",
            "http://example.com:abc",  # invalid port
            "",  # empty string
            None  # None value
        ]
        program_id = 1
        httpx_data = {'status_code': '200'}

        # Mock pool context manager
        conn = AsyncMock()
        db_manager.pool.acquire.return_value.__aenter__.return_value = conn
        
        for invalid_url in invalid_urls:
            result = await db_manager.insert_url(invalid_url, httpx_data, program_id)
            assert result is False, f"URL validation should fail for: {invalid_url}"