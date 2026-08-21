from unittest.mock import patch, MagicMock

from src.job_agent import JobTrackerAgent, JobRecord


def test_parse_job_page_basic_html():
    html = """
    <html>
      <head><title>Senior Engineer</title><meta property='og:site_name' content='Acme Corp'></head>
      <body>
        <h1>Senior Software Engineer</h1>
        <div class='location'>Remote</div>
        <span class='date'>Posted 1 day ago</span>
        <div class='description'>Build APIs and systems</div>
      </body>
    </html>
    """
    # parse_job_page pipes its extracted text through refine_summary (which shells
    # out to the claude CLI) and research_company (which hits the network). Neither
    # is under test here, and leaving them live made this a slow, flaky test that
    # failed whenever the CLI returned nothing usable. Stub them so this exercises
    # parsing only.
    with patch.object(JobTrackerAgent, "refine_summary", side_effect=lambda raw: raw), \
         patch.object(JobTrackerAgent, "research_company", return_value=""):
        record = JobTrackerAgent.parse_job_page(html, "https://example.com/job")

    assert record.title == "Senior Software Engineer"
    assert record.company == "Acme Corp"
    assert record.location == "Remote"
    assert "Posted" in record.posted_date
    assert "Build APIs" in record.summary


def test_job_record_dataclass_fields():
    record = JobRecord(
        url="https://example.com",
        title="title",
        company="company",
        location="loc",
        posted_date="today",
        summary="desc",
    )
    assert record.url == "https://example.com"
    assert record.title == "title"


def test_detect_job_board_greenhouse():
    url = "https://job-boards.greenhouse.io/justworks/jobs/7733611"
    result = JobTrackerAgent.detect_job_board(url)
    assert result == ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/justworks/jobs/7733611")


def test_detect_job_board_greenhouse_boards_subdomain():
    url = "https://boards.greenhouse.io/stripe/jobs/9876543"
    result = JobTrackerAgent.detect_job_board(url)
    assert result == ("greenhouse", "https://boards-api.greenhouse.io/v1/boards/stripe/jobs/9876543")


def test_detect_job_board_lever():
    url = "https://jobs.lever.co/acme/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    result = JobTrackerAgent.detect_job_board(url)
    assert result == ("lever", "https://api.lever.co/v0/postings/acme/a1b2c3d4-e5f6-7890-abcd-ef1234567890")


def test_detect_job_board_unknown():
    assert JobTrackerAgent.detect_job_board("https://example.com/jobs/123") is None
    assert JobTrackerAgent.detect_job_board("https://www.builtinnyc.com/job/engineer/123") is None


def test_fetch_greenhouse_job():
    api_url = "https://boards-api.greenhouse.io/v1/boards/justworks/jobs/7733611"
    original_url = "https://job-boards.greenhouse.io/justworks/jobs/7733611"
    mock_response = {
        "title": "Software Engineer, Frontend",
        "location": {"name": "New York, NY"},
        "updated_at": "2026-03-19T00:00:00Z",
        "content": "<p>Build great things.</p><ul><li>React</li><li>TypeScript</li></ul>",
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    with patch("src.job_agent.requests.get", return_value=mock_resp):
        record = JobTrackerAgent.fetch_greenhouse_job(api_url, original_url)

    assert record.title == "Software Engineer, Frontend"
    assert record.location == "New York, NY"
    assert record.posted_date == "2026-03-19"
    assert "Build great things" in record.summary
    assert record.company == "Justworks"
    assert record.url == original_url


def test_fetch_lever_job():
    api_url = "https://api.lever.co/v0/postings/acme/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    original_url = "https://jobs.lever.co/acme/a1b2c3d4-e5f6-7890-abcd-ef1234567890"
    mock_response = {
        "text": "Backend Engineer",
        "categories": {"location": "San Francisco, CA"},
        "createdAt": 1743000000000,
        "descriptionPlain": "Build scalable systems.",
    }
    mock_resp = MagicMock()
    mock_resp.json.return_value = mock_response
    with patch("src.job_agent.requests.get", return_value=mock_resp):
        record = JobTrackerAgent.fetch_lever_job(api_url, original_url)

    assert record.title == "Backend Engineer"
    assert record.location == "San Francisco, CA"
    assert record.summary == "Build scalable systems."
    assert record.company == "Acme"
    assert record.url == original_url


def test_parse_job_page_makes_no_network_or_subprocess_calls():
    """
    Parsing is pure. If refine_summary or research_company creep back into this
    path unstubbed, the unit tests start depending on a CLI and a network again.
    """
    html = "<html><head><title>T</title></head><body><h1>Engineer</h1></body></html>"
    with patch("src.job_agent.requests.get") as get, \
         patch("subprocess.run") as run, \
         patch.object(JobTrackerAgent, "refine_summary", side_effect=lambda raw: raw), \
         patch.object(JobTrackerAgent, "research_company", return_value=""):
        JobTrackerAgent.parse_job_page(html, "https://example.com/job")

    get.assert_not_called()
    run.assert_not_called()


def test_structured_children_still_win_over_raw_container_text():
    """
    The raw-text path is a last resort. When a container has real <p>/<li>
    children, those are still what get extracted — bullets keep their markers.
    """
    html = """
    <html><head><title>T</title></head><body>
      <h1>Engineer</h1>
      <div class='job-description'>
        <p>We are looking for someone to build reliable backend services at scale.</p>
        <li>Python</li>
      </div>
    </body></html>
    """
    with patch.object(JobTrackerAgent, "refine_summary", side_effect=lambda raw: raw), \
         patch.object(JobTrackerAgent, "research_company", return_value=""):
        record = JobTrackerAgent.parse_job_page(html, "https://example.com/job")

    assert "reliable backend services" in record.summary
    assert "• Python" in record.summary


def test_container_with_no_usable_content_yields_empty_summary():
    html = "<html><head><title>T</title></head><body><h1>Engineer</h1></body></html>"
    with patch.object(JobTrackerAgent, "refine_summary", side_effect=lambda raw: raw), \
         patch.object(JobTrackerAgent, "research_company", return_value=""):
        record = JobTrackerAgent.parse_job_page(html, "https://example.com/job")

    assert record.summary == ""
