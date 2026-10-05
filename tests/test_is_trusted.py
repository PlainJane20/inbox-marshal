import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from run_agent import is_trusted


def _e(domain):
    return {"sender_domain": domain}


def test_exact_match():
    assert is_trusted(_e("bank.com"), ["bank.com"])


def test_true_subdomain_matches():
    assert is_trusted(_e("mail.bank.com"), ["bank.com"])
    assert is_trusted(_e("a.b.bank.com"), ["bank.com"])


def test_lookalike_suffix_does_not_match():
    assert not is_trusted(_e("notbank.com"), ["bank.com"])
    assert not is_trusted(_e("evilbank.com"), ["bank.com"])


def test_lookalike_prefix_does_not_match():
    assert not is_trusted(_e("bank.com.evil.io"), ["bank.com"])


def test_case_insensitive():
    assert is_trusted(_e("Mail.BANK.com"), ["bank.COM"])


def test_empty_trusted_list():
    assert not is_trusted(_e("bank.com"), [])
    assert not is_trusted(_e("bank.com"), None)


def test_empty_sender_domain_never_trusted():
    assert not is_trusted(_e(""), ["bank.com"])
    assert not is_trusted(_e(""), [""])


def test_multiple_trusted_domains():
    assert is_trusted(_e("hr.corp.org"), ["bank.com", "corp.org"])
    assert not is_trusted(_e("other.org"), ["bank.com", "corp.org"])
