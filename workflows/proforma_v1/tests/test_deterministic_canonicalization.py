from workflows.proforma_v1 import canonicalization


def test_germline_null_shapes_are_not_handled_here():
    # PTBG germline-specific null collapse lives in domain_contract because it
    # depends on the selected domain contract. Generic canonicalization must not
    # guess clinical eligibility.
    assert hasattr(canonicalization, 'canonicalize_diagnosis')


def test_diagnosis_reorders_and_dedupes_without_changing_meaning():
    raw='''variants: v01\nvariant_assessments:\n  - variant_id: v02\n    classification: nonspecific\n    other_pathology: ""\n    reason: two\n  - variant_id: v01\n    classification: diagnostic_for_primary\n    other_pathology: null\n    reason: one\n'''
    text,records=canonicalization.canonicalize_diagnosis(raw,valid_variants={'v01','v02'})
    assert 'variants:\n- v01' in text
    assert text.index('variant_id: v01') < text.index('variant_id: v02')
    assert 'other_pathology: null' in text
    assert records


def test_evidence_match_wraps_only_exact_supplied_tag():
    items=[{'evidence_id':'E1','candidate_card_tags':['[card:abc]']}]
    text,records=canonicalization.canonicalize_evidence_match('matches:\n- evidence_id: E1\n  card_tags: "[card:abc]"\n',items)
    assert 'card_tags:\n  - \'[card:abc]\'' in text or 'card_tags:\n  - "[card:abc]"' in text
    assert records
    unchanged,_=canonicalization.canonicalize_evidence_match('matches:\n- evidence_id: E1\n  card_tags: "[card:wrong]"\n',items)
    assert '[card:wrong]' in unchanged


def test_evidence_audit_comments_scalar_is_representation_only():
    items=[{'evidence_id':'E1','selected_card_tags':['[card:abc]']}]
    raw='''audits:\n- evidence_id: E1\n  card_audits:\n  - card_tag: "[card:abc]"\n    card_is_element_of_reason: true\n    risk: none\n    comments: "fine"\n'''
    text,records=canonicalization.canonicalize_evidence_audit(raw,items)
    assert 'comments:\n    - fine' in text
    assert records


def test_preservation_does_not_erase_substantive_issue():
    blocks=[{'block_id':'B1'}]
    raw='''audits:\n- block_id: B1\n  preserved: true\n  issue: "meaning changed"\n'''
    text,records=canonicalization.canonicalize_preservation(raw,blocks)
    assert 'meaning changed' in text
    assert not any(r['path'].endswith('.issue') for r in records)


def test_adjudication_nulls_follow_existing_upheld_verdict_only():
    raw='''adjudications:\n- proposition_id: PX:v01\n  premise: framework:IPSS-M\n  upheld: true\n  basis: internal\n  restated_criticism: needs qualification\n'''
    text,records=canonicalization.canonicalize_adjudication_nulls(raw)
    assert 'rejection_reason: null' in text
    assert any(r['path'].endswith('.rejection_reason') for r in records)
    assert 'upheld: true' in text


def test_adjudication_rejected_row_gets_only_unused_null_fields():
    raw='''adjudications:\n- proposition_id: PX:v01\n  premise: framework:IPSS-M\n  upheld: false\n  rejection_reason: criticism unsupported\n'''
    text,records=canonicalization.canonicalize_adjudication_nulls(raw)
    assert 'basis: null' in text
    assert 'restated_criticism: null' in text
    assert 'rejection_reason: criticism unsupported' in text
    assert len(records) == 2
