# """Zensers Comprehensive Audit v2 — 8 dimensions"""
import ast, re, sys
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).parent.parent
PASS = 0; FAIL = 0; WARN = 0; INFO = 0; findings = []

def report(cat, sev, msg):
    global PASS, FAIL, WARN, INFO
    if sev == "PASS": PASS+=1
    elif sev == "FAIL": FAIL+=1;findings.append(f"  FAIL  {cat:20s} {msg}")
    elif sev == "WARN": WARN+=1;findings.append(f"  WARN  {cat:20s} {msg}")
    else: INFO+=1;findings.append(f"  INFO  {cat:20s} {msg}")

class Audit:
    def __init__(self):
        self.api = ROOT / "src/api/research_api.py"; self.t = self._read(self.api)
        self.main = ROOT / "src/api/main.py"; self.m = self._read(self.main)
        self.conversation = ROOT / "prompts/agents/conversation.md"; self.c = self._read(self.conversation)
        self.fe = ROOT / "web/src/lib/api.ts"; self.f = self._read(self.fe)
        self.panel = ROOT / "web/src/components/chat/ChatPanel.tsx"; self.p = self._read(self.panel)
        self.store = ROOT / "web/src/store/useResearchStore.ts"; self.s = self._read(self.store)
        self.progress = ROOT / "web/src/hooks/useProgress.ts"; self.r = self._read(self.progress)

    def _read(self, p):
        return p.read_text("utf-8") if p.exists() else ""

    # 1. ACTION CONSISTENCY
    def scan_actions(self):
        report("SCAN1","PASS","Actions")
        prompt_actions = set()
        m = re.search(r'"action":\s*"([^"]+)"', self.c)
        if m:
            for a in m.group(1).split("|"): prompt_actions.add(a.strip())
        handler_actions = set()
        for m in re.finditer(r'(?:if|elif)\s+action\s*==\s*"(\w+)"', self.t):
            handler_actions.add(m.group(1))
        rule_actions = set()
        for m in re.finditer(r'→\s*(\w+)', self.t):
            a=m.group(1).strip()
            if a not in ("continue_chat","enter_framework","regenerate_report","revise_report","modify_research","simple","complex","analyzing","completed","searching","produce_document","error","correct"):
                rule_actions.add(a)
        for a in sorted(handler_actions - rule_actions - {"continue_chat"}):
            report("ACTION","WARN",f"'{a}' handled no rule")
        for a in sorted(prompt_actions - handler_actions - rule_actions):
            report("ACTION","WARN",f"'{a}' in output_format no handler")

    # 2. SSE CONTRACT
    def scan_sse(self):
        report("SCAN2","PASS","SSE Events")
        progress_py = self._read(ROOT / "src/core/progress_streamer.py")
        session_py = self._read(ROOT / "src/core/session_streamer.py")
        backend = set()
        for m in re.finditer(r'SSEEventType\.(\w+)', progress_py+session_py):
            backend.add(m.group(1).lower())
        frontend = set()
        for m in re.finditer(r"case\s+'(\w+)'", self.r):
            frontend.add(m.group(1))
        for e in sorted(backend-frontend):
            report("SSE","FAIL",f"'{e}' backend only")
        for e in sorted(frontend-backend-{"chat_response","agent_message","progress","phase_start","phase_complete","complete","error","connected","heartbeat"}):
            report("SSE","FAIL",f"'{e}' frontend only")

    # 3. API CONTRACT
    def scan_api(self):
        report("SCAN3","PASS","API Routes")
        backend_routes = set()
        for m in re.finditer(r'@app\.(?:get|post|put|delete)\([\'"](/api/[^\'"]+)', self.m):
            r = re.sub(r'\{[^}]+\}','{id}',m.group(1)); backend_routes.add(r)
        frontend_routes = set()
        for m in re.finditer(r"['`](/api/[^'`${]+)", self.f):
            r = re.sub(r'\{[^}]+\}','{id}',m.group(1)); frontend_routes.add(r)
        for f in sorted(frontend_routes):
            if f not in backend_routes and 'survey' not in f:
                similar = [b for b in backend_routes if b.split('/')[:3]==f.split('/')[:3]]
                if not similar:
                    report("API","WARN",f"Frontend calls '{f}' — no matching backend route")

    # 4. HISTORY COVERAGE
    def scan_history(self):
        report("SCAN4","PASS","History")
        for m in re.finditer(r'await self\._llm_converse\((\w+)', self.t):
            line = self.t[:m.start()].count('\n')+1
            before = self.t[:m.start()]
            last_append = before.rfind('history.append')
            last_converse = before.rfind('_llm_converse')
            if last_append < last_converse:
                report("HISTORY","FAIL",f"L{line}: _llm_converse without history.append before")
        for m in re.finditer(r'return.*status.*processing', self.t):
            line = self.t[:m.start()].count('\n')+1
            before = self.t[:m.start()]
            last_hist = before.rfind('history.append')
            if last_hist > 0 and 'assistant' not in self.t[last_hist:m.start()]:
                report("HISTORY","WARN",f"L{line}: processing return may skip assistant history")

    # 5. MODE TRANSITIONS
    def scan_modes(self):
        report("SCAN5","PASS","Modes")
        mode_lines = defaultdict(list)
        for m in re.finditer(r'session\["mode"\]\s*=\s*"(\w+)"', self.t):
            line = self.t[:m.start()].count('\n')+1; mode_lines[m.group(1)].append(line)
        for l in mode_lines.get("research",[]):
            lines=self.t.split('\n');ctx='\n'.join(lines[max(0,l-3):l+2])
            if 'current_step' not in ctx: report("STATE","FAIL",f"L{l}: research no current_step")
        status_assigned = set()
        for m in re.finditer(r'session\["status"\]\s*=\s*"(\w+)"', self.t):
            status_assigned.add(m.group(1))
        status_handled = set()
        for m in re.finditer(r"status\s*===\s*'(\w+)'", self.p):
            status_handled.add(m.group(1))
        for s in sorted(status_assigned - status_handled - {"processing"}):
            report("STATE","WARN",f"Status '{s}' set by backend, not handled in frontend")

    # 6. RACE CONDITIONS
    def scan_races(self):
        report("SCAN6","PASS","Races")
        for m in re.finditer(r'asyncio\.create_task\(self\.(\w+)', self.t):
            line = self.t[:m.start()].count('\n')+1
            after = self.t[m.end():m.end()+100]
            if 'return' in after[:30]:
                report("RACE","WARN",f"L{line}: create_task+immediate return")

    # 7. FRONTEND STATE
    def scan_frontend(self):
        report("SCAN7","PASS","Frontend")
        store_keys = set()
        for m in re.finditer(r'^\s+(\w+):',self.s,re.M):
            k=m.group(1)
            if not k.startswith('set') and k not in ('true','false','null'):
                store_keys.add(k)
        used = set()
        for m in re.finditer(r'\b(\w+)\b',self.p): used.add(m.group(1))
        for k in sorted(store_keys-used):
            if k not in ('sessionId','reset','clearResearch','triggerPreviewRefresh','interrupted'):
                report("STORE","INFO",f"'{k}' in store unused in ChatPanel")

    # 8. ERROR HANDLING
    def scan_errors(self):
        report("SCAN8","PASS","Errors")
        py_files = sorted(ROOT.glob("src/**/*.py"))
        bare=0; total=0
        for f in py_files:
            t=self._read(f); total+=t.count('except'); bare+=len(re.findall(r'except\s*:',t))
            for m in re.finditer(r'try:',t):
                block=t[m.start():m.start()+1000]
                if 'catch' not in block and 'except' not in block:
                    report("ERROR","WARN",f"{f.name}: try without except nearby")

    def run(self):
        print("="*70+"\n  Zensers Comprehensive Audit (8 dimensions)\n"+"="*70)
        self.scan_actions();self.scan_sse();self.scan_api();self.scan_history()
        self.scan_modes();self.scan_races();self.scan_frontend();self.scan_errors()
        print(f"\n{'='*70}\n  PASS={PASS} WARN={WARN} FAIL={FAIL} INFO={INFO}\n{'='*70}")
        print(f"\nFindings ({FAIL+WARN}):")
        for f in findings: print(f)
        report_path = ROOT / ".sisyphus" / "audit-report.md"
        report_path.parent.mkdir(parents=True,exist_ok=True)
        with open(report_path,"w",encoding="utf-8") as f:
            f.write(f"# Audit Report\n\nPASS={PASS} WARN={WARN} FAIL={FAIL} INFO={INFO}\n\n")
            for i in findings: f.write(f"- {i}\n")
        print(f"\nSaved: {report_path}")

if __name__ == "__main__":
    Audit().run()
