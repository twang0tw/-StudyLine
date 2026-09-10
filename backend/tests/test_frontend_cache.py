from app.main import NO_CACHE_HEADERS, brand_asset, frontend_file, home_page


def test_frontend_files_do_not_use_browser_cache():
    responses = [home_page(), frontend_file("app.js"), brand_asset("studyline_tab_icon.png")]

    for response in responses:
        for header, value in NO_CACHE_HEADERS.items():
            assert response.headers[header] == value
