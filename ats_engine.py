from __future__ import annotations
import re
from collections import Counter
from typing import Any

STOP={"and","the","for","with","that","from","this","will","within","into","role","job","work","years","year","required","preferred","strong","skills","experience","responsible","including","ensure","other","related","business"}
CATEGORIES={
 "leadership_score":["lead","leadership","team","manage","director","stakeholder","mentor","coach","cross-functional"],
 "tools_score":["sql","power bi","tableau","looker","ga4","analytics","crm","excel","shopify","google","meta","seo","ppc","whatsapp"],
 "responsibility_score":["strategy","planning","execution","forecast","analysis","campaign","operations","optimize","report","ownership"],
 "commercial_score":["revenue","sales","commercial","growth","profit","pricing","acquisition","retention","conversion","roi","partnership"],
 "industry_score":["e-commerce","ecommerce","retail","grocery","digital commerce","online","platform","marketplace","aggregator"],
}
TRANSFERABLE={
 "aggregator":["third-party","partnership","platform","vendor","catalog"], "marketplace":["e-commerce","platform","merchandising","catalog"],
 "customer retention":["lifecycle","crm","re-engagement","loyalty"], "data-driven":["analysis","testing","reporting","insights"],
 "commercial negotiation":["contracts","pricing agreements","partnership","proposal","negotiat"],
 "customer experience":["customer journey","ux","personalization","engagement"],
 "cross-functional":["stakeholder","team","collaborat","operations","leadership"],
}

def _terms(t:str)->list[str]: return [w for w in re.findall(r"[A-Za-z][A-Za-z0-9+./-]{2,}",t.lower()) if w not in STOP]
def _coverage(source:str, terms:list[str])->int:
 u=list(dict.fromkeys(x.lower() for x in terms if x)); s=source.lower(); return round(100*sum(x in s for x in u)/max(1,len(u)))
def _transfer(jd:str, source:str)->int:
 jd=jd.lower(); source=source.lower(); relevant=0; points=0
 for requirement,evidence in TRANSFERABLE.items():
  if requirement in jd or any(x in jd for x in evidence):
   relevant+=1; points += 100 if requirement in source else (85 if sum(x in source for x in evidence)>=2 else 55 if any(x in source for x in evidence) else 0)
 return round(points/max(1,relevant))
def calculate_scores(job_description:str, master_resume:str, result:dict[str,Any])->dict[str,Any]:
 generated=" ".join([result.get("executive_profile","")," ".join(result.get("strategic_competencies",[]))," ".join(result.get("key_skills",[]))," ".join(b for e in result.get("experiences",[]) for b in e.get("bullets",[]))])
 full=master_resume+" "+generated; priority=[t for t,_ in Counter(_terms(job_description)).most_common(55)]
 keyword=_coverage(generated,priority); cats={k:_coverage(full,v) for k,v in CATEGORIES.items()}; transferable=_transfer(job_description,full)
 unsupported=len(result.get("unsupported_requirements",[])); enhancements=len(result.get("auto_resume_enhancements",[]))
 evidence=max(55,min(98,78+enhancements*2-unsupported*2)); parse=98
 hook=round(cats["commercial_score"]*.28+cats["leadership_score"]*.22+cats["responsibility_score"]*.17+transferable*.18+evidence*.15)
 ats=round(keyword*.28+cats["responsibility_score"]*.15+cats["tools_score"]*.08+cats["leadership_score"]*.10+cats["commercial_score"]*.12+cats["industry_score"]*.07+transferable*.10+evidence*.05+parse*.05)
 recruiter=round(hook*.30+cats["leadership_score"]*.14+cats["commercial_score"]*.18+transferable*.22+evidence*.16)
 manager=round(cats["responsibility_score"]*.19+cats["commercial_score"]*.22+cats["leadership_score"]*.17+cats["industry_score"]*.08+transferable*.22+evidence*.12)
 interview=round(recruiter*.34+manager*.30+ats*.18+hook*.10+evidence*.08-unsupported*.7)
 clamp=lambda x:max(0,min(100,int(round(x))))
 return {"ats":clamp(ats),"match":clamp(recruiter),"ats_readiness":clamp(ats),"recruiter_match":clamp(recruiter),"hiring_manager_fit":clamp(manager),"interview_probability":clamp(interview),"resume_confidence":clamp(evidence),"recruiter_hook_score":clamp(hook),"keyword_score":keyword,"evidence_score":clamp(evidence),"parseability_score":parse,"transferability_score":transferable,"hallucination_risk":clamp(100-evidence),"supported_claims":clamp(evidence),"transferable_enhancements":enhancements,"unsupported_claims":unsupported,**cats}
