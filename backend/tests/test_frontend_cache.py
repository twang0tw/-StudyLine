from unittest.mock import patch

from pymongo.errors import ServerSelectionTimeoutError

from app.main import NO_CACHE_HEADERS, brand_asset, frontend_file, health_check, home_page
from app.services import db_service


def test_frontend_files_do_not_use_browser_cache():
    responses = [home_page(), frontend_file("app.js"), brand_asset("studyline_tab_icon.png")]

    for response in responses:
        for header, value in NO_CACHE_HEADERS.items():
            assert response.headers[header] == value


def test_health_check_reports_database_failure():
    with patch.object(db_service, "ping_database", side_effect=ServerSelectionTimeoutError("offline")):
        response = health_check()

    assert response.status_code == 503
