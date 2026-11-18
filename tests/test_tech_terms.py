"""values/tech_terms.py (adrs/0015): the Tech Stack of a poller row is the
known technology names in the posting text, in order, capped, with the short
and symbol names held to whole tokens."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "values"))
from tech_terms import MAX_TERMS, TECH_TERMS, tech_stack  # noqa: E402


def test_order_and_join():
    text = "You will build services in Python and Go, deploy on AWS with Terraform and Kubernetes, and query PostgreSQL."
    assert tech_stack(text) == "Python, Go, AWS, Terraform, Kubernetes, PostgreSQL"


def test_symbol_names():
    assert tech_stack("Strong C++ and C# skills; ASP.NET a plus; Node.js services.") == "C++, C#, ASP.NET, Node.js"
    assert tech_stack("Experience with .NET and Next.js.") == ".NET, Next.js"
    assert tech_stack("Embedded C++ on an RTOS") == "C++, RTOS"


def test_whole_tokens_only():
    assert tech_stack("We value JavaScript") == "JavaScript"
    assert tech_stack("Gitter, Sparkle, Rusty, Helmet, Reacting, Dockers") == ""
    assert tech_stack("a cassandra of news and a hive of activity") == ""


def test_go_and_r_false_positives():
    for text in ("Go to market with us.", "Our Go-to-market team", "R&D lab", "Go deep on problems.",
                 "R is not listed", "We go fast"):
        assert tech_stack(text) == "", text
    assert tech_stack("Languages: Rust, Go") == "Rust, Go"
    assert tech_stack("Golang services") == "Go"
    assert tech_stack("(Go) or Java") == "Go, Java"
    assert tech_stack("Python/Go/Rust") == "Python, Go, Rust"
    assert tech_stack("Java/Go/C++") == "Java, Go, C++"
    for text in ("Go/No-Go decisions", "(Go to market)", "sales, Go to market", "No-Go, then"):
        assert tech_stack(text) == "", text


def test_versions_and_aliases():
    assert tech_stack("Modern C++17 and C++20") == "C++"
    assert tech_stack("Postgres (PostgreSQL), Golang and Go, K8s") == "PostgreSQL, Go, Kubernetes"


def test_lowercase_names_any_case():
    assert tech_stack("DBT models and Scikit-Learn") == "dbt, scikit-learn"


def test_cap_empty_and_types():
    text = ", ".join(TECH_TERMS)
    assert len(tech_stack(text).split(", ")) == MAX_TERMS
    assert tech_stack("") == "" and tech_stack(None) == "" and tech_stack(12) == ""
    assert tech_stack("Sales role, no tooling named") == ""


def test_longer_name_wins_at_same_start():
    assert tech_stack("Spring Boot and SQL Server") == "Spring Boot, SQL Server"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"TECH_TERMS:MET {len(tests)} tests")
