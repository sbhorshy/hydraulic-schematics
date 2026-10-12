from pathlib import Path
import json,re,subprocess,sys,os,time,datetime
b=Path(__file__).resolve().parent;r=b/'integration';e=b/'final-evidence';v=json.loads((e/'verification.json').read_text());head=subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip();assert head==v['commit'];assert not subprocess.check_output(['git','-C',str(r),'status','--porcelain'],text=True).strip()
assert v['results'][0]['exit_code']==1 and v['results'][1]['exit_code']==0
whole=(e/'selftest.log').read_text();assert re.search(r'timed out|TimeoutExpired|超时|超过 1800 秒',whole,re.I),whole[-1000:]
assert all('[PASS] '+c+'.' in whole for c in 'ABCDE')
initial=Path(v['results'][0]['unit_log']).read_text();pattern=r'(?ms)^(test_\w+) \(([\w.]+)\)(?:(?!^test_\w+ \().)*?\.\.\. ok$'
def passed(t):return {c+'.'+n for n,c in re.findall(pattern,t)}
assert not re.search(r'\.\.\. (FAIL|ERROR)',initial)
expected=set(json.loads((b/'expected-test-ids.json').read_text()));before=passed(initial);assert before<=expected
modules=sorted({i.split('.')[0] for i in expected-before});assert modules
command=[sys.executable,'-u','-m','unittest',*modules,'-v'];start=time.monotonic();stamp=datetime.datetime.now(datetime.timezone.utc).isoformat();log=e/'continuation-units.log'
with log.open('x') as f:
 proc=subprocess.run(command,cwd=r/'.agents/skills/hydraulic-schematic/scripts',stdout=f,stderr=subprocess.STDOUT,env=dict(os.environ,PYTHONIOENCODING='utf-8',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1'),timeout=1200)
t=log.read_text();after=passed(t);assert head==subprocess.check_output(['git','-C',str(r),'rev-parse','HEAD'],text=True).strip();assert not subprocess.check_output(['git','-C',str(r),'status','--porcelain'],text=True).strip()
result={'runtime_commit':head,'original_selftest_exit_code':1,'original_failure':'aggregate F subprocess exceeded 1800 seconds; no completed test reported FAIL/ERROR','continuation_command':command,'modules':modules,'started_at':stamp,'elapsed_seconds':round(time.monotonic()-start,3),'continuation_exit_code':proc.returncode,'initial_passed':len(before),'continuation_passed':len(after),'expected_test_count':len(expected),'observed_pass_count':len(before|after),'missing':sorted(expected-(before|after)),'unexpected':sorted((before|after)-expected),'all_test_methods_verified':proc.returncode==0 and before|after==expected,'single_selftest_invocation_passed':False}
(e/'coverage.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False),flush=True)
assert result['all_test_methods_verified']
