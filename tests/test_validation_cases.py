from validation.cases import retrieve_case, retrieve_MC


def test_stem_only():
    result = retrieve_case("1")
    assert result == "74F with anaemia."
    assert "SF3B1" not in result


def test_stem_plus_variant():
    result = retrieve_case("1A")
    assert result.startswith("74F with anaemia.")
    assert "SF3B1" in result
    assert "NEL task" not in result
    assert "Marking criteria" not in result


def test_marking_criteria_only():
    result = retrieve_MC("1A")
    assert result.startswith("- **R1C1")
    assert "NGS:" not in result
    assert "What this asks" not in result


def test_case_12c():
    result = retrieve_case("12c")
    assert "76M" in result
    assert "TP53" in result
    assert "ASXL1" in result


def test_missing_variant():
    try:
        retrieve_case("12B")
    except KeyError:
        pass
    else:
        raise AssertionError("Expected KeyError for missing Case 12B")
