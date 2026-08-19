from __future__ import annotations
import re
from difflib import SequenceMatcher
ALIASES={
 "technical program management":["program management","technical program manager","program delivery"],
 "cross-functional leadership":["cross functional teams","cross-functional teams","global teams","stakeholder alignment"],
 "roadmap alignment":["roadmap","portfolio planning","strategic planning","milestones"],
 "technical risk management":["technical risk","risk management","risk mitigation","raid"],
 "operational excellence":["operational excellence","process improvement","continuous improvement"],
 "cloud technologies":["cloud","paas","azure","aws","gcp"],
 "software development lifecycle":["sdlc","software development lifecycle","design development testing","agile delivery"],
 "engineering partnership":["engineering teams","architecture","technical lead","development lead"],
 "product partnership":["product planning","product management","business teams"],
 "program governance":["governance","governance framework","pmo","kpi reporting"],
 "executive communication":["executive reporting","senior leadership","stakeholder communication"],
 "mentoring":["mentor","mentoring","coach","coaching","knowledge transfer"],
 "distributed systems":["distributed systems","microservices","enterprise integration"],
}
def norm(s:str)->str: return re.sub(r"[^a-z0-9+#./ ]+"," ",s.lower())
def evidence_match(requirement:str,resume:str)->tuple[float,str]:
    r=norm(requirement); text=norm(resume)
    candidates=[r]+[norm(x) for x in ALIASES.get(r,[])]
    for c in candidates:
        if c and c in text: return 1.0,c
    snippets=re.split(r"[.\n;•]",text)
    best=max(((SequenceMatcher(None, " ".join(sorted(set(r.split()))), " ".join(sorted(set(s.split())))).ratio(), s.strip()) for s in snippets if len(s.strip())>10), default=(0.0, ""))
    return best if best[0]>=0.72 else (0.0,"")
def score_requirements(resume:str,requirements:list[str])->dict:
    matched=[]; partial=[]; missing=[]; weighted=0.0
    for req in dict.fromkeys(x.strip() for x in requirements if x and x.strip()):
        score,evidence=evidence_match(req,resume)
        if score>=0.9: matched.append({"requirement":req,"evidence":evidence,"confidence":round(score,2)}); weighted+=1
        elif score>=0.72: partial.append({"requirement":req,"evidence":evidence,"confidence":round(score,2)}); weighted+=0.55
        else: missing.append(req)
    total=len(matched)+len(partial)+len(missing)
    return {"score":round(100*weighted/total) if total else 0,"matched":matched,"partial":partial,"missing":missing}
