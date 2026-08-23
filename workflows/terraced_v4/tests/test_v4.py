from __future__ import annotations
import yaml
from workflows.terraced_v4 import pipeline_registry, schema_validation
from workflows.terraced_v4 import step


def test_pipelines_load():
    assert {'self','lmstudio','openrouter'} <= set(pipeline_registry.names())
    for name in pipeline_registry.names():
        plan=pipeline_registry.load(name)
        assert plan.pipeline_id==name
        for role in pipeline_registry.ROLES:
            assert pipeline_registry.binding(plan,role).role==role


def test_prognosis_allows_multiple_effects_and_requires_coverage():
    doc={
        'favorable':[],
        'adverse':[{'variants':['v01'],'reason':'adverse association'},{'variants':['v01'],'reason':'second distinct adverse proposition'}],
        'other':[], 'uncertain':[], 'no_effect':['v02'],
        'overall':{'classification':'not calculable','reason':'required inputs unavailable'},
    }
    assert 'valid' in schema_validation.validate_prognosis(yaml.safe_dump(doc),{'v01','v02'})


def test_prognosis_rejects_positive_and_no_effect_overlap():
    doc={'favorable':[],'adverse':[{'variants':['v01'],'reason':'x'}],'other':[],'uncertain':[],'no_effect':['v01'],'overall':{'classification':'x','reason':'y'}}
    try: schema_validation.validate_prognosis(yaml.safe_dump(doc),{'v01'})
    except ValueError as exc: assert 'both effect and no_effect' in str(exc)
    else: raise AssertionError('expected overlap failure')


def test_germline_requires_clinical_support_for_suspect_or_uncertain():
    doc={'suspect':[{'variants':['v01'],'reason':'known germline gene and VAF compatible'}],'uncertain':[],'not_suspect':['v02'],'clinical_support':[{'variants':['v01'],'support':'unknown','reason':'family history not supplied'}]}
    assert 'valid' in schema_validation.validate_germline(yaml.safe_dump(doc),{'v01','v02'})


def test_evidence_match_does_not_validate_quote_exactness():
    text=yaml.safe_dump({'card_id':'C1','source':'IPSS-M','quote':'slightly normalized wording'})
    assert 'valid' in schema_validation.validate_evidence_match(text,{'C1'})


def test_evidence_audit_requires_actionable_comment_for_obvious_mismatch():
    text=yaml.safe_dump({'obvious_mismatch':True,'risk':'none','comments':[]})
    try: schema_validation.validate_evidence_audit(text)
    except ValueError as exc: assert 'actionable feedback' in str(exc)
    else: raise AssertionError('expected missing-comment failure')


def test_risk_log_is_idempotent_across_resume(tmp_path):
    kwargs=dict(stage='evidence',risk_type='citation_fidelity',message='same concern',schema_element='PX-01',attempts=1,action='retained_pending_human_review',human_review='recommended')
    first=step._risk(tmp_path,**kwargs); second=step._risk(tmp_path,**kwargs)
    doc=yaml.safe_load((tmp_path/'logs'/'risk_log.yaml').read_text())
    assert first==second=='R001'
    assert len(doc['risks'])==1


def test_summary_plan_audit_structure_and_fallback():
    audit=yaml.safe_dump({'preserved':False,'issues':[{'target':'diagnosis-1','issue':'Dropped qualifying molecular basis.'}]})
    assert 'valid' in step._validate_summary_plan_audit(audit)
    statements=[{'statement_id':'S0001','domain':'diagnosis','statement':'Diagnosis A.','card_tags':[]},{'statement_id':'S0002','domain':'prognosis','statement':'Risk B.','card_tags':[]}]
    plan=step._fallback_summary_plan(statements)
    blocks=step.runtime.build_summary_blocks(plan,statements)
    assert [x['source_statement_ids'] for x in blocks]==[['S0001'],['S0002']]


def test_diagnosis_colon_mapping_reports_actionable_serialization_issue():
    from scripts.core.validated_model_task import ValidationFailure
    broken='''who5:\n  diagnoses:\n    - schema_disease: AML\n      status: established\n      diagnosis: AML\n      reasons: [blast threshold met]\nicc:\n  diagnoses:\n    - status: established\n      diagnosis: AML, NOS\n      reasons: [blast threshold met]\nconcordance:\n  answer: concordant\n  reasons:\n    - Clinical distinction: nomenclature differs\nconcurrent_second_diagnosis:\n  answer: none supported\n  reasons: [no discordant case facts]\n'''
    try:
        schema_validation.validate_diagnosis(broken,allowed_diseases={'AML'})
    except ValidationFailure as exc:
        assert len(exc.issues)==1
        issue=exc.issues[0]
        assert issue.path=='concordance.reasons[0]'
        assert issue.repair_class=='serialization'
        rendered=issue.render(1)
        assert 'YAML parsed mapping' in rendered
        assert "unquoted ': '" in rendered
        assert 'Received:' in rendered and 'Expected:' in rendered
    else:
        raise AssertionError('expected serialization failure')


def test_prognosis_accumulates_serialization_and_content_errors():
    from scripts.core.validated_model_task import ValidationFailure
    broken='''favorable: []\nadverse:\n  - variants: v01\n    reason:\n      FLT3: adverse marker\nother: []\nuncertain: []\nno_effect: []\noverall:\n  classification: null\n  reason: ""\n'''
    try:
        schema_validation.validate_prognosis(broken,{'v01','v02'})
    except ValidationFailure as exc:
        paths=[x.path for x in exc.issues]
        assert 'adverse[0].variants' in paths
        assert 'adverse[0].reason' in paths
        assert 'prognosis' in paths
        assert 'overall.classification' in paths
        assert 'overall.reason' in paths
        assert sum(x.repair_class=='serialization' for x in exc.issues)==2
        assert sum(x.repair_class=='content' for x in exc.issues)>=3
    else:
        raise AssertionError('expected aggregated validation failure')


def test_schema_serialization_repair_fixes_shape_then_preserves_content_failures():
    from scripts.core import syntax_repair
    from scripts.core.validated_model_task import ValidationFailure
    broken='''favorable: []\nadverse:\n  - variants: v01\n    reason:\n      FLT3: adverse marker\nother: []\nuncertain: []\nno_effect: []\noverall:\n  classification: null\n  reason: ""\n'''
    repaired='''favorable: []\nadverse:\n  - variants: [v01]\n    reason: "FLT3: adverse marker"\nother: []\nuncertain: []\nno_effect: []\noverall:\n  classification: null\n  reason: ""\n'''
    validator=lambda t:schema_validation.validate_prognosis(t,{'v01','v02'})
    prompts=[]
    def feedback(exc):
        if not isinstance(exc,ValidationFailure): return None
        rows=[x for x in exc.issues if x.repair_class=='serialization']
        return '\n'.join(x.render(i) for i,x in enumerate(rows,1)) if rows else None
    def fake_model(prompt,attempt):
        prompts.append(prompt)
        return repaired
    result=syntax_repair.repair_schema_serialization(
        broken,format_name='yaml',validator=validator,serialization_feedback=feedback,
        model_repair=fake_model,model_attempts=2,
    )
    assert len(prompts)==1
    assert 'adverse[0].variants' in prompts[0]
    assert 'adverse[0].reason' in prompts[0]
    assert 'Do NOT fix missing clinical content' in prompts[0]
    try:
        validator(result.text)
    except ValidationFailure as exc:
        assert all(x.repair_class!='serialization' for x in exc.issues)
        paths=[x.path for x in exc.issues]
        assert 'prognosis' in paths
        assert 'overall.classification' in paths
        assert 'overall.reason' in paths
    else:
        raise AssertionError('content defects should remain for originating task')


def test_validate_candidate_routes_schema_serialization_to_generic_syntax_repair(monkeypatch,tmp_path):
    broken='''who5:\n  diagnoses:\n    - schema_disease: AML\n      status: established\n      diagnosis: AML\n      reasons: [blast threshold met]\nicc:\n  diagnoses:\n    - status: established\n      diagnosis: AML, NOS\n      reasons: [blast threshold met]\nconcordance:\n  answer: concordant\n  reasons:\n    - Clinical distinction: nomenclature differs\nconcurrent_second_diagnosis:\n  answer: none supported\n  reasons: [no discordant case facts]\n'''
    fixed=broken.replace('    - Clinical distinction: nomenclature differs','    - "Clinical distinction: nomenclature differs"')
    prompts=[]
    monkeypatch.setattr(step,'_syntax_callback',lambda work,binding,call_id,total_attempts: (lambda prompt,attempt:(prompts.append(prompt) or fixed)))
    validator=lambda t:schema_validation.validate_diagnosis(t,allowed_diseases={'AML'})
    candidate,msg=step._validate_candidate(
        tmp_path,candidate=broken,fmt='yaml',call_id='diagnosis-pass-01',syntax_binding=object(),
        validator=validator,syntax_attempts=10,
    )
    assert 'valid' in msg
    assert len(prompts)==1
    assert 'concordance.reasons[0]' in prompts[0]
    assert "unquoted ': '" in prompts[0]
    assert candidate==fixed


def test_diagnosis_pass2_uses_cumulative_old_and_new_cmcs(monkeypatch,tmp_path):
    """If WHO5 pass 1 changes CMC, WHO5 pass 2 recalls old+new CMC evidence."""
    case={'bootstrap_cmcs':['MDS'],'variants':[]}
    monkeypatch.setattr(step,'_allowed_diseases',lambda work:{'AML','MDS'})
    monkeypatch.setattr(step.runtime,'case_genes',lambda case:[])
    draws=[]
    monkeypatch.setattr(step,'_draw_diagnosis_cards',lambda eligible,genes,cmcs:(draws.append(list(cmcs)) or []))
    monkeypatch.setattr(step,'_filter_diagnosis_authority',lambda cards,authority:list(cards))
    who={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML','reasons':['r']}]}
    icc={'diagnoses':[{'status':'established','diagnosis':'AML, NOS','reasons':['r']}],'comparison_with_who5':{'significantly_different':False,'explanation':'not significantly different'}}
    other={'concurrent_second_diagnosis':{'answer':'none supported','reasons':['r']}}
    def fake_model_call(work,**kwargs):
        if kwargs['call_id'].startswith('diagnosis-who5'): doc=who
        elif kwargs['call_id']=='diagnosis-icc': doc=icc
        else: doc=other
        kwargs['output'].parent.mkdir(parents=True,exist_ok=True)
        kwargs['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
        return kwargs['output'].read_text()
    monkeypatch.setattr(step,'_model_call',fake_model_call)
    final,final_cmcs,_cards=step.stage_diagnosis(tmp_path,case,[],profile='self')
    assert draws[0]==['MDS']
    assert draws[1]==['MDS','AML']
    assert draws[2]==['MDS','AML']  # ICC candidate draw
    assert draws[3]==['MDS','AML']  # other-diagnosis evidence pool for later matching
    routing_paths=list((tmp_path/'intermediates').glob('*/routing.json'))
    assert len(routing_paths)==1
    routing=__import__('json').loads(routing_paths[0].read_text())
    assert routing['pass_2_cmc_history']==['MDS','AML']
    assert routing['diagnostic_cmc_history']==['MDS','AML']
    assert routing['who5_authoritative_pass']==2
    assert final_cmcs==['AML']
    assert final['who5']==who


def test_diagnosis_skips_who5_pass2_when_cmc_unchanged(monkeypatch,tmp_path):
    case={'bootstrap_cmcs':['AML'],'variants':[]}
    monkeypatch.setattr(step,'_allowed_diseases',lambda work:{'AML'})
    monkeypatch.setattr(step.runtime,'case_genes',lambda case:[])
    monkeypatch.setattr(step,'_draw_diagnosis_cards',lambda eligible,genes,cmcs:[])
    monkeypatch.setattr(step,'_filter_diagnosis_authority',lambda cards,authority:list(cards))
    who={'diagnoses':[{'schema_disease':'AML','status':'established','diagnosis':'AML','reasons':['r']}]}
    icc={'diagnoses':[{'status':'established','diagnosis':'AML, NOS','reasons':['r']}],'comparison_with_who5':{'significantly_different':False,'explanation':'not significantly different'}}
    other={'concurrent_second_diagnosis':{'answer':'none supported','reasons':['r']}}
    calls=[]
    def fake_model_call(work,**kwargs):
        calls.append(kwargs['call_id'])
        doc=who if kwargs['call_id']=='diagnosis-who5-pass-01' else (icc if kwargs['call_id']=='diagnosis-icc' else other)
        kwargs['output'].parent.mkdir(parents=True,exist_ok=True); kwargs['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake_model_call)
    step.stage_diagnosis(tmp_path,case,[],profile='self')
    assert calls==['diagnosis-who5-pass-01','diagnosis-icc','diagnosis-other-considerations']


def test_failed_syntax_repair_attempt_is_copied_to_error_log(tmp_path):
    from scripts.core import syntax_repair
    failed=syntax_repair.SyntaxRepairAttempt(
        index=1,
        prompt='repair this',
        response='broken: [yaml',
        parser_error='expected closing bracket',
    )
    successful=syntax_repair.SyntaxRepairAttempt(
        index=2,
        prompt='repair again',
        response='broken: yaml',
    )
    step._archive_failed_syntax_attempts(tmp_path,'diagnosis-pass-01',[failed,successful])
    err=tmp_path/'logs'/'errors'/'diagnosis-pass-01-syntax-attempt-01.txt'
    assert err.is_file()
    text=err.read_text()
    assert 'broken: [yaml' in text
    assert 'expected closing bracket' in text
    assert 'repair this' in text
    assert not (tmp_path/'logs'/'errors'/'diagnosis-pass-01-syntax-attempt-02.txt').exists()


def test_diagnosis_authority_filters_match_v3_defaults():
    who=step._diagnosis_authority_publications('who5')
    icc=step._diagnosis_authority_publications('icc')
    assert who=={'khoury-2022-leukemia-36-1703'}
    assert icc=={'arber-2022-blood-140-1200'}


def test_batched_evidence_match_and_audit_validators():
    items=[
        {'evidence_id':'E0001','candidate_card_ids':['C1','C2']},
        {'evidence_id':'E0002','candidate_card_ids':['C3']},
    ]
    match={'matches':[
        {'evidence_id':'E0001','card_id':'C2','source':'ELN 2022','quote':'q1'},
        {'evidence_id':'E0002','card_id':'C3','source':'Smith et al.','quote':'q2'},
    ]}
    assert 'valid' in schema_validation.validate_evidence_match_batch(yaml.safe_dump(match),items)
    audit={'audits':[
        {'evidence_id':'E0001','obvious_mismatch':False,'risk':'none','comments':[]},
        {'evidence_id':'E0002','obvious_mismatch':True,'risk':'warning','comments':['wrong disease context']},
    ]}
    assert 'valid' in schema_validation.validate_evidence_audit_batch(yaml.safe_dump(audit),items)


def test_summary_plan_split_merge_and_deterministic_blocks():
    statements=[
        {'statement_id':'S0001','domain':'diagnosis','statement':'Diagnosis A because X and Y.','card_tags':['[card:1]']},
        {'statement_id':'S0002','domain':'diagnosis','statement':'ICC label B.','card_tags':['[card:2]']},
        {'statement_id':'S0003','domain':'prognosis','statement':'Risk C.','card_tags':['[card:3]']},
    ]
    plan={
        'dispositions':[
            {'statement_id':'S0001','decision':'split','reason':None},
            {'statement_id':'S0002','decision':'include','reason':None},
            {'statement_id':'S0003','decision':'include','reason':None},
        ],
        'parts':[
            {'statement_id':'S0003','group':'later','split_text':None},
            {'statement_id':'S0001','group':'dx-a','split_text':'Diagnosis A because X.'},
            {'statement_id':'S0002','group':'dx-a','split_text':None},
            {'statement_id':'S0001','group':'dx-b','split_text':'Diagnosis A also depends on Y.'},
        ],
    }
    assert 'validated' in step.runtime.validate_summary_plan_doc(plan,statements)
    blocks=step.runtime.build_summary_blocks(plan,statements)
    assert [b['block_id'] for b in blocks]==['diagnosis-1','diagnosis-2','prognosis-1']
    assert blocks[0]['source_statement_ids']==['S0001','S0002']
    assert blocks[1]['source_statement_ids']==['S0001']


def test_model_usage_tally(tmp_path):
    step._record_usage(tmp_path,'call-a','model-x',1,{'prompt_tokens':100,'completion_tokens':20,'total_tokens':120},role='diagnosis')
    step._record_usage(tmp_path,'call-b','model-x',1,None,role='syntax_repair')
    summary=step._usage_summary(tmp_path)
    assert summary['calls']==2
    assert summary['reported_calls']==1
    assert summary['unreported_calls']==1
    assert summary['totals']=={'prompt_tokens':100,'completion_tokens':20,'total_tokens':120}


def test_stage_evidence_batches_initial_match_and_audit(monkeypatch,tmp_path):
    elements=[
        {'schema_id':'PX-A','domain':'prognosis','proposition':'A','reasons':['r1'],'variants':['v01'],'evidence_domain':'prognosis'},
        {'schema_id':'TX-A','domain':'treatment','proposition':'B','reasons':['r2'],'variants':['v01'],'evidence_domain':'treatment'},
    ]
    card1={'card_id':'C1','category':'prognosis','genes':['G'],'diseases':['AML'],'interpretation':'r1 evidence'}
    card2={'card_id':'C2','category':'treatment','genes':['G'],'diseases':['AML'],'interpretation':'r2 evidence'}
    cards={'prognosis':[card1],'treatment':[card2]}; reg={'v01':{'gene':'G'}}
    monkeypatch.setattr(step.card_identity,'tag_by_id',lambda manifest:{'C1':'T1','C2':'T2'})
    calls=[]
    def fake_model_call(work,**kwargs):
        calls.append(kwargs['call_id']); kwargs['output'].parent.mkdir(parents=True,exist_ok=True)
        if kwargs['call_id']=='evidence-match-batch-a1':
            doc={'matches':[{'evidence_id':'E0001','card_id':'C1','source':'S1','quote':'Q1'},{'evidence_id':'E0002','card_id':'C2','source':'S2','quote':'Q2'}]}
        elif kwargs['call_id']=='evidence-audit-batch-a1':
            doc={'audits':[{'evidence_id':'E0001','obvious_mismatch':False,'risk':'none','comments':[]},{'evidence_id':'E0002','obvious_mismatch':False,'risk':'none','comments':[]}]}
        else: raise AssertionError(kwargs['call_id'])
        kwargs['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake_model_call)
    enriched=step.stage_evidence(tmp_path,elements,cards,reg,{},'self')
    assert calls==['evidence-match-batch-a1','evidence-audit-batch-a1']
    assert [e['evidence'][0]['card_id'] for e in enriched]==['C1','C2']


def test_stage_summary_uses_one_plan_and_one_paraphrase_batch(monkeypatch,tmp_path):
    statements=[
        {'statement_id':'S0001','domain':'diagnosis','statement':'Diagnosis A.','card_tags':['[card:1]']},
        {'statement_id':'S0002','domain':'prognosis','statement':'Risk B.','card_tags':['[card:2]']},
    ]
    calls=[]
    def fake_model_call(work,**kwargs):
        calls.append(kwargs['call_id']); kwargs['output'].parent.mkdir(parents=True,exist_ok=True)
        cid=kwargs['call_id']
        if cid=='summary-plan':
            doc={'dispositions':[{'statement_id':'S0001','decision':'include','reason':None},{'statement_id':'S0002','decision':'include','reason':None}], 'parts':[{'statement_id':'S0001','group':'g1','split_text':None},{'statement_id':'S0002','group':'g2','split_text':None}]}
        elif cid=='summary-plan-audit': doc={'preserved':True,'issues':[]}
        elif cid=='paraphrase-batch': doc={'sentences':[{'block_id':'diagnosis-1','sentence':'Diagnosis A.'},{'block_id':'prognosis-1','sentence':'Risk B.'}]}
        elif cid=='paraphrase-audit-batch': doc={'audits':[{'block_id':'diagnosis-1','preserved':True,'issue':None},{'block_id':'prognosis-1','preserved':True,'issue':None}]}
        else: raise AssertionError(cid)
        kwargs['output'].write_text(yaml.safe_dump(doc,sort_keys=False))
    monkeypatch.setattr(step,'_model_call',fake_model_call)
    final=step.stage_summary(tmp_path,statements,'self')
    assert calls==['summary-plan','summary-plan-audit','paraphrase-batch','paraphrase-audit-batch']
    assert [r['sentence_id'] for r in final['sentences']]==['diagnosis-1','prognosis-1']


def test_model_call_records_provider_usage(monkeypatch,tmp_path):
    from workflows.terraced_v4.model_binding import Binding
    from workflows.terraced_v4 import model_client
    binding=Binding(pipeline='test',role='diagnosis',kind='openai-compatible',model='m',base_url='http://x')
    monkeypatch.setattr(step,'_profile',lambda work,profile,role: binding if role!='syntax_repair' else Binding(pipeline='test',role='syntax_repair',kind='openai-compatible',model='m',base_url='http://x'))
    monkeypatch.setattr(model_client,'complete_messages',lambda b,m:model_client.Completion('x: ok\n',{'prompt_tokens':11,'completion_tokens':3,'total_tokens':14}))
    out=tmp_path/'out.yaml'
    step._model_call(tmp_path,call_id='usage-call',role='diagnosis',prompt='p',output=out,validator=lambda t:'valid',profile='test')
    summary=step._usage_summary(tmp_path)
    assert summary['totals']['total_tokens']==14
    ledger=__import__('json').loads((tmp_path/'logs'/'model-usage.json').read_text())
    assert ledger['calls'][0]['operation']=='usage-call'
    assert ledger['calls'][0]['role']=='diagnosis'


def test_treatment_no_effect_mapping_is_content_not_syntax():
    """The brief-2 nightmare shape requires deleting fields, so syntax must not touch it."""
    from scripts.core.validated_model_task import ValidationFailure
    broken=yaml.safe_dump({
        'drug_target':[], 'drug_resistance':[], 'other':[],
        'no_effect':[{
            'variants':['v01','v02','v03','v04'],
            'therapy':'none',
            'reason':'No supported treatment implication.',
        }],
    },sort_keys=False)
    try:
        schema_validation.validate_treatment(broken,{'v01','v02','v03','v04'})
    except ValidationFailure as exc:
        issue=next(x for x in exc.issues if x.path=='treatment.no_effect[0]')
        assert issue.repair_class=='content'
        assert 'bare supplied variant ID strings' in issue.required_fix
        assert not any(x.path=='treatment.no_effect[0]' and x.repair_class=='serialization' for x in exc.issues)
    else:
        raise AssertionError('expected treatment schema failure')


def test_proforma_syntax_cap_restarts_original_task_from_scratch(monkeypatch,tmp_path):
    from workflows.terraced_v4.model_binding import Binding
    from workflows.terraced_v4 import model_client
    binding=Binding(pipeline='test',role='ptbg',kind='openai-compatible',model='m',base_url='http://x')
    syntax_binding=Binding(pipeline='test',role='syntax_repair',kind='openai-compatible',model='m',base_url='http://x')
    monkeypatch.setattr(step,'_profile',lambda work,profile,role: syntax_binding if role=='syntax_repair' else binding)
    messages=[]
    responses=iter(['broken artifact','good: yes\n'])
    def fake_complete(_binding,msgs):
        messages.append(msgs)
        return model_client.Completion(next(responses),{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2})
    monkeypatch.setattr(model_client,'complete_messages',fake_complete)
    prepare_calls=[]
    def fake_prepare(work,raw,fmt,call_id,syntax_binding,*,syntax_attempts):
        prepare_calls.append((raw,call_id,syntax_attempts))
        if raw=='broken artifact':
            raise step.SyntaxCycleExhausted('five syntax repairs failed',feedback='wrong serialization shape')
        return raw
    monkeypatch.setattr(step,'_prepare_structured',fake_prepare)
    out=tmp_path/'proforma.yaml'
    result=step._model_call(tmp_path,call_id='treatment',role='ptbg',prompt='ORIGINAL PROFORMA',output=out,validator=lambda t:'valid',profile='test',proforma=True)
    assert result=='good: yes\n'
    assert len(messages)==2
    assert prepare_calls[0][2]==5
    assert all(m['role']!='assistant' for m in messages[1])
    assert any('Regenerate the complete proforma from scratch' in m['content'] for m in messages[1] if m['role']=='user')
    assert any(p.name=='treatment-proforma-invalid.txt' for p in (tmp_path/'logs'/'errors').iterdir())


def test_proforma_full_rewrite_cap_is_three(monkeypatch,tmp_path):
    from workflows.terraced_v4.model_binding import Binding
    from workflows.terraced_v4 import model_client
    from scripts.core.validated_model_task import ValidationFailure, ValidationIssue
    binding=Binding(pipeline='test',role='ptbg',kind='openai-compatible',model='m',base_url='http://x')
    monkeypatch.setattr(step,'_profile',lambda work,profile,role: binding)
    calls=[]
    def fake_complete(_binding,msgs):
        calls.append(msgs)
        return model_client.Completion('answer: wrong\n',None)
    monkeypatch.setattr(model_client,'complete_messages',fake_complete)
    monkeypatch.setattr(step,'_prepare_structured',lambda work,raw,fmt,call_id,syntax_binding,syntax_attempts: raw)
    def bad_validator(_text):
        raise ValidationFailure('test proforma',[ValidationIssue('answer','wrong clinical/schema value','return the required value',repair_class='content')])
    try:
        step._model_call(tmp_path,call_id='prognosis',role='ptbg',prompt='P',output=tmp_path/'out.yaml',validator=bad_validator,profile='test',proforma=True)
    except step.StepFailure as exc:
        assert 'initial proforma plus 3 full proforma rewrite(s)' in str(exc)
    else:
        raise AssertionError('expected proforma rewrite exhaustion')
    assert len(calls)==4  # initial generation + three complete rewrites


def test_proforma_runs_five_real_syntax_attempts_then_full_fresh_rewrite(monkeypatch,tmp_path):
    from workflows.terraced_v4.model_binding import Binding
    from workflows.terraced_v4 import model_client
    diagnosis_binding=Binding(pipeline='test',role='diagnosis',kind='openai-compatible',model='m',base_url='http://x')
    syntax_binding=Binding(pipeline='test',role='syntax_repair',kind='openai-compatible',model='m',base_url='http://x')
    monkeypatch.setattr(step,'_profile',lambda work,profile,role: syntax_binding if role=='syntax_repair' else diagnosis_binding)
    broken='''concurrent_second_diagnosis:\n  answer: none supported\n  reasons:\n    - Clinical distinction: nomenclature differs\n'''
    fixed='''concurrent_second_diagnosis:\n  answer: none supported\n  reasons:\n    - "Clinical distinction: nomenclature differs"\n'''
    counts={'diagnosis':0,'syntax_repair':0}; seen=[]
    def fake_complete(binding,messages):
        counts[binding.role]+=1; seen.append((binding.role,messages))
        if binding.role=='syntax_repair':
            return model_client.Completion(broken,None)  # deliberately never repairs generation 1
        return model_client.Completion(broken if counts['diagnosis']==1 else fixed,None)
    monkeypatch.setattr(model_client,'complete_messages',fake_complete)
    out=tmp_path/'other.yaml'
    result=step._model_call(tmp_path,call_id='diagnosis-other-considerations',role='diagnosis',prompt='ORIGINAL',output=out,validator=schema_validation.validate_other_diagnosis,profile='test',proforma=True)
    assert counts=={'diagnosis':2,'syntax_repair':5}
    assert result==fixed
    second=[msgs for role,msgs in seen if role=='diagnosis'][1]
    assert all(m['role']!='assistant' for m in second)
    assert any('Regenerate the complete proforma from scratch' in m['content'] for m in second if m['role']=='user')
