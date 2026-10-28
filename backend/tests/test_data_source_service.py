"""
Unit tests for DataSourceService.

Crypto helpers, the Sangfor service, TerminalService (audit), and ComplianceService
(recalculation) are all mocked so no real firewall / DB / Redis is required.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.data_source import DataSource, DataSourceBinding
from app.schemas.data_source import (
    ConnectionTestResult,
    DataSourceCreate,
    DataSourceUpdate,
)
from app.services.data_source_service import DataSourceService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_result(scalar=None, rows=None, all_rows=None, first=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar
    if rows is not None:
        result.scalars.return_value.all.return_value = rows
    if first is not None:
        result.scalars.return_value.first.return_value = first
    if all_rows is not None:
        result.all.return_value = all_rows
    return result


def make_source(id_=1, name="src", type_="arp_ssh", tag="lab", config="ENC", enabled=True):
    s = MagicMock(spec=DataSource)
    s.id = id_
    s.name = name
    s.type = type_
    s.tag = tag
    s.config = config
    s.enabled = enabled
    s.last_sync_at = None
    s.last_sync_status = None
    s.last_sync_error = None
    return s


def make_terminal(status="blocked", ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF",
                  source_tag="lab", firewall_tag="fw1"):
    t = MagicMock()
    t.ip_address = ip
    t.mac_address = mac
    t.mac_address_normalized = "AABBCCDDEEFF"
    t.status = status
    t.source_tag = source_tag
    t.firewall_tag = firewall_tag
    t.compliance_status = "unknown"
    t.comments = None
    return t


def make_blacklist(ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF",
                   firewall_tag="fw1", source_tag="lab"):
    b = MagicMock()
    b.ip_address = ip
    b.mac_address = mac
    b.mac_address_normalized = "AABBCCDDEEFF"
    b.firewall_tag = firewall_tag
    b.source_tag = source_tag
    return b


def make_binding(id_=1, arp_source_tag="lab", firewall_tag="fw1"):
    b = MagicMock(spec=DataSourceBinding)
    b.id = id_
    b.arp_source_tag = arp_source_tag
    b.firewall_tag = firewall_tag
    return b


def make_async_client(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    client = MagicMock()
    client.get = AsyncMock(return_value=resp)
    client.post = AsyncMock(return_value=resp)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    return client


def set_exec_sequence(mock_db, results):
    it = iter(results)

    async def _side(stmt):
        try:
            return next(it)
        except StopIteration:
            return make_result()

    mock_db.execute = AsyncMock(side_effect=_side)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_db(mock_async_session):
    return mock_async_session


@pytest.fixture
def service(mock_db):
    return DataSourceService(mock_db)


# ===========================================================================
# create_data_source
# ===========================================================================

class TestCreateDataSource:
    @pytest.mark.asyncio
    async def test_invalid_type(self, service):
        data = DataSourceCreate(name="s", type="bogus", tag="lab", config={})
        with pytest.raises(ValueError):
            await service.create_data_source(data)

    @pytest.mark.asyncio
    async def test_duplicate_name(self, service):
        data = DataSourceCreate(name="s", type="arp_ssh", tag="lab", config={})
        existing = make_source(name="s", tag="other")
        with patch.object(service, "_get_by_name_or_tag", AsyncMock(return_value=existing)):
            with pytest.raises(ValueError, match="name"):
                await service.create_data_source(data)

    @pytest.mark.asyncio
    async def test_duplicate_tag(self, service):
        data = DataSourceCreate(name="s", type="arp_ssh", tag="lab", config={})
        existing = make_source(name="other", tag="lab")
        with patch.object(service, "_get_by_name_or_tag", AsyncMock(return_value=existing)):
            with pytest.raises(ValueError, match="tag"):
                await service.create_data_source(data)

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        data = DataSourceCreate(name="s", type="arp_ssh", tag="lab", config={"host": "x"})
        with patch.object(service, "_get_by_name_or_tag", AsyncMock(return_value=None)), \
             patch("app.services.data_source_service.encrypt_config", return_value="ENCRYPTED"):
            result = await service.create_data_source(data)

        assert isinstance(result, DataSource)
        assert result.config == "ENCRYPTED"
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()
        mock_db.refresh.assert_called_once()


# ===========================================================================
# update_data_source
# ===========================================================================

class TestUpdateDataSource:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        data = DataSourceUpdate(name="new")
        assert await service.update_data_source(99, data) is None

    @pytest.mark.asyncio
    async def test_invalid_type(self, service, mock_db):
        source = make_source()
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        data = DataSourceUpdate(type="bogus")
        with pytest.raises(ValueError):
            await service.update_data_source(1, data)

    @pytest.mark.asyncio
    async def test_duplicate_name(self, service, mock_db):
        source = make_source(name="old")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        existing = make_source(name="new")
        data = DataSourceUpdate(name="new")
        with patch.object(service, "_get_by_field", AsyncMock(return_value=existing)):
            with pytest.raises(ValueError, match="name"):
                await service.update_data_source(1, data)

    @pytest.mark.asyncio
    async def test_tag_change_raises(self, service, mock_db):
        source = make_source(tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        data = DataSourceUpdate(tag="newtag")
        with pytest.raises(ValueError, match="tag"):
            await service.update_data_source(1, data)

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        source = make_source(config="ENC")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        data = DataSourceUpdate(name="new", type="arp_api", config={"url": "http://x"}, enabled=False)
        with patch.object(service, "_get_by_field", AsyncMock(return_value=None)), \
             patch("app.services.data_source_service.decrypt_config", return_value={"url": "http://x"}):
            result = await service.update_data_source(1, data)

        assert result is source
        assert source.name == "new"
        assert source.type == "arp_api"
        mock_db.commit.assert_called_once()
        mock_db.expunge.assert_called_once()


# ===========================================================================
# delete_data_source
# ===========================================================================

class TestDeleteDataSource:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.delete_data_source(99) is False

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        source = make_source()
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        assert await service.delete_data_source(1) is True
        mock_db.delete.assert_called_once_with(source)
        mock_db.commit.assert_called_once()


# ===========================================================================
# getters
# ===========================================================================

class TestGetById:
    @pytest.mark.asyncio
    async def test_found_decrypts(self, service, mock_db):
        source = make_source(config="ENC")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        with patch("app.services.data_source_service.decrypt_config", return_value={"k": "v"}) as dec:
            result = await service.get_data_source_by_id(1)
        assert result.config == {"k": "v"}
        mock_db.expunge.assert_called_once_with(source)
        dec.assert_called_once_with("ENC")

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.get_data_source_by_id(99) is None

    @pytest.mark.asyncio
    async def test_no_config_no_decrypt(self, service, mock_db):
        source = make_source(config=None)
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        result = await service.get_data_source_by_id(1)
        assert result is source
        mock_db.expunge.assert_not_called()


class TestGetByTag:
    @pytest.mark.asyncio
    async def test_found(self, service, mock_db):
        source = make_source(config="ENC", tag="lab")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        with patch("app.services.data_source_service.decrypt_config", return_value={}):
            result = await service.get_data_source_by_tag("lab")
        assert result is source

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.get_data_source_by_tag("nope") is None


class TestListDataSources:
    @pytest.mark.asyncio
    async def test_no_filter(self, service, mock_db):
        source = make_source(config="ENC")
        mock_db.execute = AsyncMock(return_value=make_result(rows=[source]))
        with patch("app.services.data_source_service.decrypt_config", return_value={}):
            result = await service.list_data_sources()
        assert result == [source]

    @pytest.mark.asyncio
    async def test_type_and_enabled_filter(self, service, mock_db):
        source = make_source(config=None)
        mock_db.execute = AsyncMock(return_value=make_result(rows=[source]))
        result = await service.list_data_sources(type="arp_ssh", enabled=True)
        assert result == [source]


# ===========================================================================
# update_sync_status
# ===========================================================================

class TestUpdateSyncStatus:
    @pytest.mark.asyncio
    async def test_found(self, service, mock_db):
        source = make_source()
        mock_db.execute = AsyncMock(return_value=make_result(scalar=source))
        await service.update_sync_status(1, "success", None)
        assert source.last_sync_status == "success"
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        await service.update_sync_status(99, "success")
        mock_db.commit.assert_not_called()


# ===========================================================================
# test_connection
# ===========================================================================

class TestConnection:
    @pytest.mark.asyncio
    async def test_not_found(self, service):
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=None)):
            result = await service.test_connection(1)
        assert result.success is False
        assert "not found" in result.message

    @pytest.mark.asyncio
    async def test_ssh_type(self, service):
        source = make_source(type_="arp_ssh")
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=source)), \
             patch.object(service, "_test_ssh_connection", AsyncMock(return_value=ConnectionTestResult(success=True, message="ok"))):
            result = await service.test_connection(1)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_api_type(self, service):
        source = make_source(type_="arp_api")
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=source)), \
             patch.object(service, "_test_api_connection", AsyncMock(return_value=ConnectionTestResult(success=False, message="nope"))):
            result = await service.test_connection(1)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_sangfor_success_updates_last_sync_at(self, service, mock_db):
        source = make_source(type_="sangfor")
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=source)), \
             patch.object(service, "_test_sangfor_connection", AsyncMock(return_value=ConnectionTestResult(success=True, message="ok"))):
            result = await service.test_connection(1)
        assert result.success is True
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_unknown_type(self, service):
        source = make_source(type_="bogus")
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=source)):
            result = await service.test_connection(1)
        assert result.success is False
        assert "Unknown data source type" in result.message

    @pytest.mark.asyncio
    async def test_exception(self, service):
        source = make_source(type_="arp_ssh")
        with patch.object(service, "get_data_source_by_id", AsyncMock(return_value=source)), \
             patch.object(service, "_test_ssh_connection", AsyncMock(side_effect=Exception("boom"))):
            result = await service.test_connection(1)
        assert result.success is False
        assert "Connection test failed" in result.message


# ===========================================================================
# _test_ssh_connection
# ===========================================================================

class TestSshConnection:
    @pytest.mark.asyncio
    async def test_success(self, service):
        source = make_source(type_="arp_ssh", config={"host": "10.0.0.1", "port": 22, "username": "u", "password": "p"})
        with patch("paramiko.SSHClient") as cls, patch("paramiko.AutoAddPolicy"):
            client = MagicMock()
            cls.return_value = client
            result = await service._test_ssh_connection(source)
        assert result.success is True
        client.connect.assert_called_once()
        client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_generic_exception(self, service):
        source = make_source(type_="arp_ssh", config={"host": "10.0.0.1"})
        with patch("paramiko.SSHClient") as cls:
            client = MagicMock()
            client.connect.side_effect = Exception("auth failed")
            cls.return_value = client
            result = await service._test_ssh_connection(source)
        assert result.success is False
        assert "SSH connection failed" in result.message

    @pytest.mark.asyncio
    async def test_import_error(self, service):
        source = make_source(type_="arp_ssh", config={"host": "10.0.0.1"})
        with patch.dict("sys.modules", {"paramiko": None}):
            result = await service._test_ssh_connection(source)
        assert result.success is False
        assert "paramiko library not installed" in result.message


# ===========================================================================
# _test_api_connection
# ===========================================================================

class TestApiConnection:
    @pytest.mark.asyncio
    async def test_success_get(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x", "headers": {}, "auth_type": "", "token": ""})
        with patch("httpx.AsyncClient", return_value=make_async_client(200)):
            result = await service._test_api_connection(source)
        assert result.success is True

    @pytest.mark.asyncio
    async def test_error_status(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x", "headers": {}, "auth_type": "", "token": ""})
        with patch("httpx.AsyncClient", return_value=make_async_client(500)):
            result = await service._test_api_connection(source)
        assert result.success is False

    @pytest.mark.asyncio
    async def test_bearer_auth(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x", "headers": {}, "auth_type": "bearer", "token": "T"})
        client = make_async_client(200)
        with patch("httpx.AsyncClient", return_value=client):
            await service._test_api_connection(source)
        assert client.get.call_args.kwargs["headers"]["Authorization"] == "Bearer T"

    @pytest.mark.asyncio
    async def test_header_auth(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x", "headers": {}, "auth_type": "header", "token": "T", "header_name": "X-Key"})
        client = make_async_client(200)
        with patch("httpx.AsyncClient", return_value=client):
            await service._test_api_connection(source)
        assert client.get.call_args.kwargs["headers"]["X-Key"] == "T"

    @pytest.mark.asyncio
    async def test_header_auth_default_header_name(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x", "headers": {}, "auth_type": "header", "token": "T"})
        client = make_async_client(200)
        with patch("httpx.AsyncClient", return_value=client):
            await service._test_api_connection(source)
        assert client.get.call_args.kwargs["headers"]["X-Auth-Token"] == "T"

    @pytest.mark.asyncio
    async def test_post_method(self, service):
        source = make_source(type_="arp_api", config={"method": "POST", "url": "http://x", "headers": {}, "auth_type": "", "token": ""})
        client = make_async_client(200)
        with patch("httpx.AsyncClient", return_value=client):
            result = await service._test_api_connection(source)
        assert result.success is True
        client.post.assert_called_once()
        client.get.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception(self, service):
        source = make_source(type_="arp_api", config={"method": "GET", "url": "http://x"})
        with patch("httpx.AsyncClient", side_effect=Exception("boom")):
            result = await service._test_api_connection(source)
        assert result.success is False
        assert "API connection failed" in result.message


# ===========================================================================
# _test_sangfor_connection
# ===========================================================================

class TestSangforConnection:
    @pytest.mark.asyncio
    async def test_success(self, service):
        source = make_source(type_="sangfor", tag="fw1", config={"base_url": "https://fw"})
        with patch("app.services.sangfor_service.SangforService") as cls, \
             patch("app.services.event_emitter.emit_firewall_connection_restored", AsyncMock()) as emit:
            svc = MagicMock()
            svc.test_connection = AsyncMock(return_value={"success": True, "message": "ok", "details": {}})
            svc.close = AsyncMock()
            cls.return_value = svc
            result = await service._test_sangfor_connection(source)
        assert result.success is True
        emit.assert_called_once_with("fw1")

    @pytest.mark.asyncio
    async def test_exception(self, service):
        source = make_source(type_="sangfor", config={"base_url": "https://fw"})
        with patch("app.services.sangfor_service.SangforService", side_effect=Exception("boom")):
            result = await service._test_sangfor_connection(source)
        assert result.success is False
        assert "Sangfor AF connection failed" in result.message


# ===========================================================================
# create_binding
# ===========================================================================

class TestCreateBinding:
    @pytest.mark.asyncio
    async def test_arp_not_found(self, service):
        with patch.object(service, "get_data_source_by_tag", AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="ARP data source"):
                await service.create_binding("lab", "fw1")

    @pytest.mark.asyncio
    async def test_arp_wrong_type(self, service):
        arp = make_source(type_="sangfor", tag="lab")
        with patch.object(service, "get_data_source_by_tag", AsyncMock(return_value=arp)):
            with pytest.raises(ValueError, match="not an ARP source"):
                await service.create_binding("lab", "fw1")

    @pytest.mark.asyncio
    async def test_fw_not_found(self, service):
        arp = make_source(type_="arp_ssh", tag="lab")
        with patch.object(service, "get_data_source_by_tag", AsyncMock(side_effect=[arp, None])):
            with pytest.raises(ValueError, match="Firewall data source"):
                await service.create_binding("lab", "fw1")

    @pytest.mark.asyncio
    async def test_fw_wrong_type(self, service):
        arp = make_source(type_="arp_ssh", tag="lab")
        fw = make_source(type_="arp_api", tag="fw1")
        with patch.object(service, "get_data_source_by_tag", AsyncMock(side_effect=[arp, fw])):
            with pytest.raises(ValueError, match="not a firewall"):
                await service.create_binding("lab", "fw1")

    @pytest.mark.asyncio
    async def test_duplicate(self, service, mock_db):
        arp = make_source(type_="arp_ssh", tag="lab")
        fw = make_source(type_="sangfor", tag="fw1")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=MagicMock()))
        with patch.object(service, "get_data_source_by_tag", AsyncMock(side_effect=[arp, fw])):
            with pytest.raises(ValueError, match="already exists"):
                await service.create_binding("lab", "fw1")

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        arp = make_source(type_="arp_ssh", tag="lab")
        fw = make_source(type_="sangfor", tag="fw1")
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        with patch.object(service, "get_data_source_by_tag", AsyncMock(side_effect=[arp, fw])), \
             patch("app.services.compliance_service.ComplianceService") as cs_cls:
            cs = MagicMock()
            cs.recalculate_all_compliance = AsyncMock()
            cs_cls.return_value = cs
            result = await service.create_binding("lab", "fw1")

        assert isinstance(result, DataSourceBinding)
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()


# ===========================================================================
# delete_binding / list_bindings / get_firewall_tags
# ===========================================================================

class TestDeleteBinding:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.delete_binding(99) is False

    @pytest.mark.asyncio
    async def test_success(self, service, mock_db):
        binding = make_binding()
        mock_db.execute = AsyncMock(return_value=make_result(scalar=binding))
        assert await service.delete_binding(1) is True
        mock_db.delete.assert_called_once_with(binding)


class TestListBindings:
    @pytest.mark.asyncio
    async def test_no_filter(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(rows=[make_binding()]))
        assert len(await service.list_bindings()) == 1

    @pytest.mark.asyncio
    async def test_with_filter(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(rows=[]))
        assert await service.list_bindings(arp_source_tag="lab") == []


class TestGetFirewallTags:
    @pytest.mark.asyncio
    async def test_returns_tags(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(all_rows=[("fw1",), ("fw2",)]))
        assert await service.get_firewall_tags_for_arp("lab") == ["fw1", "fw2"]


# ===========================================================================
# preview_delete_data_source
# ===========================================================================

class TestPreviewDeleteDataSource:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        result = await service.preview_delete_data_source(99)
        assert result["can_delete"] is False
        assert result["reason"] == "Data source not found"

    @pytest.mark.asyncio
    async def test_arp_source(self, service, mock_db):
        source = make_source(type_="arp_ssh", tag="lab", name="lab-source")
        terminals = [make_terminal(status="blocked"), make_terminal(status="unblocked")]
        bl = [make_blacklist(firewall_tag="fw1")]
        bindings = [make_binding()]
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=terminals),
            make_result(rows=bl),
            make_result(rows=bindings),
        ])
        result = await service.preview_delete_data_source(1)
        assert result["can_delete"] is True
        assert result["affected"]["terminals"] == 2
        assert result["affected"]["blocked_terminals"] == 1
        assert result["affected"]["blacklist_entries"] == 1
        assert any("够" in w or "解封" in w or "封堵" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_sangfor_reachable(self, service, mock_db):
        source = make_source(type_="sangfor", tag="fw1", name="fw", config="ENC")
        terminals = [make_terminal(status="blocked")]
        bl = [make_blacklist(firewall_tag="fw1")]
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=terminals),
            make_result(rows=bl),
            make_result(rows=[make_binding()]),
        ])
        svc = MagicMock()
        svc.test_connection = AsyncMock(return_value={"success": True, "message": "ok", "details": {}})
        svc.close = AsyncMock()
        with patch("app.services.data_source_service.decrypt_config", return_value={"base_url": "https://fw", "username": "u", "password": "p"}), \
             patch("app.services.sangfor_service.SangforService", return_value=svc):
            result = await service.preview_delete_data_source(1)
        assert result["can_delete"] is True

    @pytest.mark.asyncio
    async def test_sangfor_unreachable(self, service, mock_db):
        source = make_source(type_="sangfor", tag="fw1", name="fw", config="ENC")
        terminals = [make_terminal(status="blocked")]
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=terminals),
            make_result(rows=[make_blacklist(firewall_tag="fw1")]),
            make_result(rows=[]),
        ])
        svc = MagicMock()
        svc.test_connection = AsyncMock(return_value={"success": False})
        svc.close = AsyncMock()
        with patch("app.services.data_source_service.decrypt_config", return_value={"base_url": "https://fw"}), \
             patch("app.services.sangfor_service.SangforService", return_value=svc):
            result = await service.preview_delete_data_source(1)
        assert result["can_delete"] is False
        assert result["reason"] is not None

    @pytest.mark.asyncio
    async def test_sangfor_no_blocked_skips_connection(self, service, mock_db):
        source = make_source(type_="sangfor", tag="fw1", name="fw", config="ENC")
        terminals = [make_terminal(status="unblocked")]
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=terminals),
            make_result(rows=[]),    # blacklist
            make_result(rows=[]),    # bindings
        ])
        result = await service.preview_delete_data_source(1)
        assert result["can_delete"] is True
        assert result["affected"]["blocked_terminals"] == 0

    @pytest.mark.asyncio
    async def test_sangfor_config_none_connection_fails(self, service, mock_db):
        source = make_source(type_="sangfor", tag="fw1", name="fw", config=None)
        terminals = [make_terminal(status="blocked")]
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=terminals),
            make_result(rows=[make_blacklist(firewall_tag="fw1")]),
            make_result(rows=[]),
        ])
        result = await service.preview_delete_data_source(1)
        assert result["can_delete"] is False
        assert any("连接失败" in w for w in result["warnings"])


# ===========================================================================
# safe_delete_data_source
# ===========================================================================

class TestSafeDeleteDataSource:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.safe_delete_data_source(99) is False

    @pytest.mark.asyncio
    async def test_arp_no_blocked_terminals(self, service, mock_db, mock_redis):
        source = make_source(type_="arp_ssh", tag="lab", name="lab-source")
        mock_redis.keys = AsyncMock(return_value=[])
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=[]),  # blocked terminals
            make_result(),  # delete blacklist
            make_result(),  # delete terminals
            make_result(),  # delete bindings
        ])
        assert await service.safe_delete_data_source(1) is True
        mock_db.delete.assert_called_once_with(source)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_arp_with_blocked_terminal_unblocks(self, service, mock_db, mock_redis):
        source = make_source(type_="arp_ssh", tag="lab", name="lab-source")
        terminal = make_terminal(status="blocked", ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF", source_tag="lab")
        bl_entry = make_blacklist(ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF", firewall_tag="fw1", source_tag="lab")
        fw_source = make_source(type_="sangfor", tag="fw1", config="ENC")
        mock_redis.keys = AsyncMock(return_value=[])

        set_exec_sequence(mock_db, [
            make_result(scalar=source),          # source lookup
            make_result(rows=[terminal]),        # blocked terminals
            make_result(rows=[bl_entry]),        # blacklist per terminal
            make_result(),                        # delete blacklist
            make_result(),                        # delete terminals
            make_result(),                        # delete bindings
        ])

        svc = MagicMock()
        svc.unblock_ip = AsyncMock(return_value={"code": 0, "message": "", "data": {"unblocked": [], "skipped": [], "errors": []}})
        svc.close = AsyncMock()

        with patch.object(service, "get_data_source_by_tag", AsyncMock(return_value=fw_source)), \
             patch("app.services.data_source_service.decrypt_config", return_value={"base_url": "https://fw"}), \
             patch("app.services.sangfor_service.SangforService", return_value=svc):
            assert await service.safe_delete_data_source(1) is True

        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert terminal.compliance_status == "unknown"
        svc.unblock_ip.assert_called_once()
        mock_db.delete.assert_called_once_with(source)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_sangfor_deletion(self, service, mock_db, mock_redis):
        source = make_source(type_="sangfor", tag="fw1", name="fw", config="ENC")
        terminal = make_terminal(status="blocked", firewall_tag="fw1")
        bl_entry = make_blacklist(ip="10.0.0.1", firewall_tag="fw1", source_tag="lab")
        mock_redis.keys = AsyncMock(return_value=[])

        set_exec_sequence(mock_db, [
            make_result(scalar=source),          # source lookup
            make_result(rows=[terminal]),        # affected terminals
            make_result(rows=[bl_entry]),        # blacklist entries
            make_result(),                        # delete blacklist
            make_result(),                        # delete bindings
        ])

        svc = MagicMock()
        svc.unblock_ip = AsyncMock(return_value={"code": 0, "message": "", "data": {"unblocked": [], "skipped": [], "errors": []}})
        svc.close = AsyncMock()

        with patch("app.services.data_source_service.decrypt_config", return_value={"base_url": "https://fw"}), \
             patch("app.services.sangfor_service.SangforService", return_value=svc):
            assert await service.safe_delete_data_source(1) is True

        assert terminal.firewall_tag is None
        assert terminal.status == "unblocked"
        assert terminal.compliance_status == "unknown"
        svc.unblock_ip.assert_called_once()
        mock_db.delete.assert_called_once_with(source)

    @pytest.mark.asyncio
    async def test_audit_log_when_username(self, service, mock_db, mock_redis):
        source = make_source(type_="arp_ssh", tag="lab", name="lab-source")
        mock_redis.keys = AsyncMock(return_value=[])
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=[]),   # blocked terminals
            make_result(),  # delete blacklist
            make_result(),  # delete terminals
            make_result(),  # delete bindings
        ])

        with patch("app.services.terminal_service.TerminalService") as ts_cls:
            ts = MagicMock()
            ts.log_action = AsyncMock()
            ts_cls.return_value = ts
            assert await service.safe_delete_data_source(1, username="admin", client_ip="1.2.3.4") is True

        ts.log_action.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_add_before_commit_atomic(self, service, mock_db, mock_redis):
        """业务删除仍在事务内提交；审计已解耦到独立会话。

        P0 将 ``log_action`` 改为通过独立 ``async_session_factory`` 立即提交，
        使审计记录即便业务事务回滚也能落库（审计必记）。因此 ``self.db`` 上
        不再出现审计的 ``add``，只保留业务删除的 ``commit``。
        """
        source = make_source(type_="arp_ssh", tag="lab", name="lab-source")
        mock_redis.keys = AsyncMock(return_value=[])
        set_exec_sequence(mock_db, [
            make_result(scalar=source),
            make_result(rows=[]),  # blocked terminals
            make_result(),  # delete blacklist
            make_result(),  # delete terminals
            make_result(),  # delete bindings
        ])

        events = []
        mock_db.add = MagicMock(side_effect=lambda *a, **k: events.append("add"))
        mock_db.commit = AsyncMock(side_effect=lambda: events.append("commit"))

        with patch("app.services.terminal_service.SangforService"):
            assert await service.safe_delete_data_source(1, username="admin", client_ip="1.2.3.4") is True

        # 审计 add 不再落在业务 session 上；仅业务删除的 commit 出现一次。
        assert events == ["commit"]
        mock_db.add.assert_not_called()


# ===========================================================================
# preview_delete_binding
# ===========================================================================

class TestPreviewDeleteBinding:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        result = await service.preview_delete_binding(99)
        assert result["can_delete"] is False
        assert result["reason"] == "Binding not found"

    @pytest.mark.asyncio
    async def test_no_blocked(self, service, mock_db):
        binding = make_binding()
        set_exec_sequence(mock_db, [
            make_result(scalar=binding),
            make_result(rows=[]),  # blacklist entries
        ])
        result = await service.preview_delete_binding(1)
        assert result["can_delete"] is True
        assert result["affected"]["bindings"] == 1

    @pytest.mark.asyncio
    async def test_with_blocked(self, service, mock_db):
        binding = make_binding()
        bl = [
            make_blacklist(ip="10.0.0.1", firewall_tag="fw1", source_tag="lab"),
            make_blacklist(ip="10.0.0.2", firewall_tag="fw1", source_tag="lab"),
        ]
        set_exec_sequence(mock_db, [
            make_result(scalar=binding),
            make_result(rows=bl),
        ])
        result = await service.preview_delete_binding(1)
        assert result["can_delete"] is True
        assert result["affected"]["blocked_terminals"] == 2
        assert result["affected"]["blacklist_entries"] == 2
        assert any("解封" in a for a in result["actions"])


# ===========================================================================
# safe_delete_binding
# ===========================================================================

class TestSafeDeleteBinding:
    @pytest.mark.asyncio
    async def test_not_found(self, service, mock_db):
        mock_db.execute = AsyncMock(return_value=make_result(scalar=None))
        assert await service.safe_delete_binding(99) is False

    @pytest.mark.asyncio
    async def test_success_with_blocked(self, service, mock_db):
        binding = make_binding(arp_source_tag="lab", firewall_tag="fw1")
        bl_entry = make_blacklist(ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF", firewall_tag="fw1", source_tag="lab")
        terminal = make_terminal(status="blocked", ip="10.0.0.1", mac="AA:BB:CC:DD:EE:FF", firewall_tag="fw1")
        fw_source = make_source(type_="sangfor", tag="fw1", config="ENC")

        set_exec_sequence(mock_db, [
            make_result(scalar=binding),    # binding lookup
            make_result(rows=[bl_entry]),   # blacklist entries
            make_result(first=terminal),    # terminal lookup (scalars().first())
            make_result(rows=[]),           # other blacklist (none)
        ])

        svc = MagicMock()
        svc.unblock_ip = AsyncMock(return_value={"code": 0, "message": "", "data": {"unblocked": [], "skipped": [], "errors": []}})
        svc.close = AsyncMock()

        with patch.object(service, "get_data_source_by_tag", AsyncMock(return_value=fw_source)), \
             patch("app.services.data_source_service.decrypt_config", return_value={"base_url": "https://fw"}), \
             patch("app.services.sangfor_service.SangforService", return_value=svc), \
             patch("app.services.compliance_service.ComplianceService") as cs_cls:
            cs = MagicMock()
            cs.recalculate_all_compliance = AsyncMock()
            cs_cls.return_value = cs
            assert await service.safe_delete_binding(1) is True

        assert terminal.status == "unblocked"
        assert terminal.firewall_tag is None
        assert terminal.compliance_status == "unknown"
        svc.unblock_ip.assert_called_once()
        cs.recalculate_all_compliance.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_add_before_commit_atomic(self, service, mock_db):
        """unbind_datasource 业务删除提交仍在事务内；审计已解耦到独立会话。"""
        binding = make_binding(arp_source_tag="lab", firewall_tag="fw1")
        set_exec_sequence(mock_db, [
            make_result(scalar=binding),   # binding lookup
            make_result(rows=[]),           # blacklist entries (none)
        ])

        events = []
        mock_db.add = MagicMock(side_effect=lambda *a, **k: events.append("add"))
        mock_db.commit = AsyncMock(side_effect=lambda: events.append("commit"))

        with patch("app.services.terminal_service.SangforService"), \
             patch("app.services.compliance_service.ComplianceService") as cs_cls:
            cs = MagicMock()
            cs.recalculate_all_compliance = AsyncMock()
            cs_cls.return_value = cs
            assert await service.safe_delete_binding(1, username="admin", client_ip="1.2.3.4") is True

        # 审计 add 不再落在业务 session 上；仅业务删除的 commit 出现一次。
        assert events == ["commit"]
        mock_db.add.assert_not_called()