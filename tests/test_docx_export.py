from core.docx_export import build_docx

SAMPLE = """CANDIDATE NAME
HEAD OF PRODUCT & PLATFORM ENGINEERING
Product Scale | Platform Reliability | Engineering Operating Models
Bengaluru, India | +91 00000 00000 | candidate@example.com | linkedin.com/in/candidate
PROFESSIONAL SUMMARY
Engineering leader with 17+ years of experience building and scaling revenue-critical platforms.
SELECTED CAREER HIGHLIGHTS
- Scaled a national platform supporting 250+ workflow parameters and 800+ operating locations.
- Improved daily throughput from 5,000 to 20,000+ transactions.
CORE LEADERSHIP & TECHNICAL EXPERTISE
Product Engineering | Platform Strategy | Cloud Architecture | Program Governance
PROFESSIONAL EXPERIENCE
HEAD OF ENGINEERING | EXAMPLE COMPANY | Bengaluru | Dec 2022 - Present
- Directed product and platform engineering across multiple business-critical systems.
- Institutionalized engineering OKRs, release governance and delivery metrics.
DIRECTOR OF ENGINEERING | EXAMPLE SAAS COMPANY | Bengaluru | Jun 2018 - Dec 2022
- Modernized globally scaled SaaS platforms and improved delivery predictability.
EARLIER PROFESSIONAL EXPERIENCE
Engineering Manager | Example Learning Platform
EDUCATION & PROFESSIONAL DEVELOPMENT
Master of Computer Applications | Example University
TECHNICAL SKILLS
Cloud-Native Architecture | Kubernetes | CI/CD | APIs | Data Platforms
"""


def test_docx_export():
    data = build_docx(SAMPLE)
    assert data[:2] == b"PK"
    assert len(data) > 10000
