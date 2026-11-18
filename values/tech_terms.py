"""Technology names a posting mentions, for the Tech Stack line of a channel
post (adrs/0015). Pure: no I/O.

hiring.cafe sends its own technical_tools list; poller rows have only the
posting text, so this picks known names out of it. autojob's data/taxonomy.json
is resume-skill vocabulary (practices included) in a private submodule, which
is why this list is its own home.

A name with an uppercase letter, digit or symbol matches case-sensitively as a
whole token. An all-lowercase name matches in any case. "Go" counts only inside
a list or as "Golang", and bare "R" is left out, so "Go to market" and "R&D"
give nothing.
"""

import re

MAX_TERMS = 12

TECH_TERMS = (
    # languages
    "Python", "Java", "JavaScript", "TypeScript", "C++", "C#", "Golang", "Go", "Rust", "Scala", "Kotlin",
    "Swift", "Ruby", "PHP", "Perl", "MATLAB", "Julia", "Haskell", "Elixir", "Erlang", "Clojure", "Lua",
    "Bash", "PowerShell", "SQL", "Verilog", "VHDL", "Fortran", "Objective-C", "Dart", "Solidity", "COBOL",
    # web and backend
    "React", "Angular", "Vue", "Next.js", "Node.js", "Express.js", "Django", "Flask", "FastAPI", "Spring Boot", "Rails", ".NET", "ASP.NET", "GraphQL", "gRPC", "REST", "HTML", "CSS", "Tailwind",
    "Redux", "jQuery", "Svelte", "WebSockets", "Kafka", "RabbitMQ", "Celery",
    # data stores
    "PostgreSQL", "Postgres", "MySQL", "MariaDB", "SQLite", "MongoDB", "Redis", "Cassandra", "DynamoDB",
    "Elasticsearch", "OpenSearch", "Snowflake", "BigQuery", "Redshift", "Databricks", "ClickHouse",
    "Oracle", "SQL Server", "Neo4j", "Pinecone",
    # data and ML
    "Spark", "PySpark", "Airflow", "dbt", "Flink", "Hadoop", "Hive", "Presto", "Trino", "Iceberg",
    "Pandas", "NumPy", "SciPy", "scikit-learn", "PyTorch", "TensorFlow", "Keras", "JAX", "XGBoost",
    "Hugging Face", "LangChain", "CUDA", "OpenCV", "Jupyter", "Tableau", "Power BI", "Looker", "Microsoft Excel",
    # cloud and infra
    "AWS", "Azure", "GCP", "Google Cloud", "Lambda", "EC2", "S3", "EKS", "ECS", "Kubernetes", "K8s",
    "Docker", "Terraform", "Ansible", "Pulumi", "CloudFormation", "Helm", "Jenkins", "GitHub Actions",
    "GitLab CI", "CircleCI", "ArgoCD", "Prometheus", "Grafana", "Datadog", "Splunk", "Nginx", "Linux",
    "Unix", "Git", "CI/CD", "OpenTelemetry",
    # embedded, hardware, other
    "ROS", "FPGA", "RTOS", "Embedded C", "LabVIEW", "Simulink", "SolidWorks", "Unreal Engine",
    "Salesforce", "ServiceNow", "SAP", "Selenium", "Playwright", "Cypress", "Jest", "pytest", "JUnit",
    "OAuth", "Figma", "Jira",
)

_EDGE = r"(?<![A-Za-z0-9_+#.])"
_TAIL = r"(?![A-Za-z0-9_+#]|\.[A-Za-z0-9])"
_GO = re.compile(r"(?:(?<=[,/(])|(?<=[,/(]\s))Go\b(?![-']|/No|\s+to\b)|(?<![A-Za-z0-9-])Go(?=\s*[,/)])(?!/No)")
_VERSIONED = ("C++",)  # C++17, C++20
SAME = {"Postgres": "PostgreSQL", "Golang": "Go", "K8s": "Kubernetes"}


def _pattern(term):
    if term == "Go":
        return _GO
    flags = 0 if re.search(r"[A-Z0-9+#./]", term) else re.I
    tail = r"(?:\d{2})?" + _TAIL if term in _VERSIONED else _TAIL
    return re.compile(_EDGE + re.escape(term).replace(r"\ ", r"\s+") + tail, flags)


_PATTERNS = [(t, _pattern(t)) for t in TECH_TERMS]


def tech_stack(text):
    """The TECH_TERMS names found in text, in order of first appearance, at
    most MAX_TERMS, joined by ', '. '' when none."""
    if not isinstance(text, str) or not text:
        return ""
    found = []
    for term, pat in _PATTERNS:
        m = pat.search(text)
        if m:
            found.append((m.start(), -len(term), term))
    found.sort()
    names, spans = [], []
    for start, _, term in found:
        name = SAME.get(term, term)
        if name in names or any(s <= start < e for s, e in spans):  # ".NET" inside "ASP.NET"
            continue
        names.append(name)
        spans.append((start, start + len(term)))
        if len(names) == MAX_TERMS:
            break
    return ", ".join(names)
