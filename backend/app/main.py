import csv, io, os, random, secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import numpy as np
import pandas as pd
from fastapi import Depends, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr, Field
from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.errors import PyMongoError

app = FastAPI(title="Healthcare Analytics API", version="1.0.0", description="MongoDB-powered healthcare operations and educational risk estimates.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:3000"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

SECRET = os.getenv("JWT_SECRET", "development-secret-change-me")
pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
ROLES = {"ADMIN", "DOCTOR", "RECEPTIONIST", "LAB TECHNICIAN", "PHARMACIST"}
try:
    client = MongoClient(os.getenv("MONGODB_URL", "mongodb://localhost:27017"), serverSelectionTimeoutMS=1200)
    client.admin.command("ping")
    db = client[os.getenv("MONGODB_DB", "healthcare_analytics")]
except PyMongoError:
    db = None
memory: dict[str, list[dict]] = {k: [] for k in ["users","patients","doctors","appointments","admissions","diagnoses","lab_reports","medicines","prescriptions","predictions","etl_jobs","notifications","audit_logs"]}

def now(): return datetime.now(timezone.utc)
def clean(x):
    if isinstance(x, dict): return {k: clean(v) for k,v in x.items()}
    if isinstance(x, list): return [clean(v) for v in x]
    if hasattr(x, "__str__") and x.__class__.__name__ == "ObjectId": return str(x)
    if isinstance(x, datetime): return x.isoformat()
    return x
def find(col, query=None):
    query = query or {}
    if db is not None: return [clean(x) for x in db[col].find(query).sort("created_at", DESCENDING)]
    return [x.copy() for x in memory[col] if all(x.get(k)==v for k,v in query.items())]
def one(col, id):
    rows = find(col, {"id": id})
    return rows[0] if rows else None
def insert(col, item):
    item = {**item, "id": item.get("id", secrets.token_urlsafe(10)), "created_at": now().isoformat(), "updated_at": now().isoformat()}
    if db is not None: db[col].insert_one(item)
    else: memory[col].append(item)
    return clean(item)
def update(col, id, patch):
    if not one(col,id): raise HTTPException(404, "Record not found")
    patch = {**patch, "updated_at": now().isoformat()}
    if db is not None: db[col].update_one({"id":id},{"$set":patch})
    else:
        for x in memory[col]:
            if x["id"]==id: x.update(patch)
    return one(col,id)
def remove(col,id):
    if not one(col,id): raise HTTPException(404,"Record not found")
    if db is not None: db[col].delete_one({"id":id})
    else: memory[col][:] = [x for x in memory[col] if x["id"] != id]
def audit(user, action, module, details=""):
    insert("audit_logs", {"user":user.get("name","System"),"action":action,"module":module,"details":details,"timestamp":now().isoformat()})
def require(*roles):
    def dep(c: HTTPAuthorizationCredentials = Depends(security)):
        try: u = jwt.decode(c.credentials, SECRET, algorithms=["HS256"])
        except JWTError: raise HTTPException(401, "Invalid or expired session")
        if roles and u.get("role") not in roles: raise HTTPException(403, "You do not have permission for this action")
        return u
    return dep
class Login(BaseModel): email: EmailStr; password: str
class Register(BaseModel): name: str; email: EmailStr; password: str = Field(min_length=8); role: str = "RECEPTIONIST"
class Record(BaseModel): data: dict[str, Any]
class Prediction(BaseModel): patient_id: str; disease: str; inputs: dict[str, Any]

@app.on_event("startup")
def seed():
    if find("users"): return
    for role,email,name in [("ADMIN","admin@carepulse.demo","Aarav Mehta"),("DOCTOR","doctor@carepulse.demo","Dr. Maya Iyer"),("RECEPTIONIST","reception@carepulse.demo","Nina Shah"),("LAB TECHNICIAN","lab@carepulse.demo","Rohan Das"),("PHARMACIST","pharmacy@carepulse.demo","Priya Nair")]:
        insert("users", {"name":name,"email":email,"role":role,"password_hash":pwd.hash("Demo@123")})
    diseases=["Diabetes","Hypertension","Heart Disease","Asthma","Kidney Disease"]
    doctors=[]
    for i in range(20): doctors.append(insert("doctors",{"doctor_id":f"DOC-{100+i}","name":f"Dr. {'Maya' if i==0 else 'Alex'} {'Iyer' if i==0 else f'Patel {i+1}'}","department":["Cardiology","General Medicine","Neurology","Pediatrics"][i%4],"specialization":diseases[i%5],"phone":f"+91 90000 {10000+i}","email":f"doctor{i+1}@carepulse.demo","availability":"Available","experience":f"{3+i%18} years"}))
    patients=[]
    for i in range(120): patients.append(insert("patients",{"patient_id":f"PAT-{1000+i}","first_name":["Asha","Arjun","Meera","Kabir","Isha"][i%5],"last_name":f"Kumar {i+1}","age":18+i%65,"gender":"Female" if i%2 else "Male","blood_group":["O+","A+","B+","AB+"][i%4],"phone":f"+91 98{i:08d}","email":f"patient{i+1}@example.demo","existing_diseases":[diseases[i%5]],"risk_level":["LOW","MEDIUM","HIGH"][i%3],"registration_date":(now()-timedelta(days=i*2)).date().isoformat()}))
    for i in range(130): insert("appointments",{"patient_id":patients[i%120]["id"],"patient_name":patients[i%120]["first_name"]+" "+patients[i%120]["last_name"],"doctor_id":doctors[i%20]["id"],"doctor_name":doctors[i%20]["name"],"department":doctors[i%20]["department"],"appointment_date":(now()+timedelta(days=(i%21)-8)).isoformat(),"status":["Scheduled","Confirmed","Completed","Cancelled"][i%4],"queue_number":i+1})
    for i in range(55): insert("medicines",{"medicine_id":f"MED-{200+i}","medicine_name":f"{['Paracetamol','Metformin','Atorvastatin','Amoxicillin','Amlodipine'][i%5]} {i+1}","category":"General","manufacturer":"CarePharm","batch_number":f"B-{5000+i}","quantity":i%3*15+5,"unit_price":round(12+i*1.7,2),"expiry_date":(now()+timedelta(days=30+i*7)).date().isoformat(),"minimum_stock_level":15})
    for i in range(65):
        p=patients[i]; insert("lab_reports",{"patient_id":p["id"],"patient_name":p["first_name"]+" "+p["last_name"],"test_type":["CBC","Blood Sugar","Lipid Profile","Kidney Function Test"][i%4],"result_status":["Normal","Abnormal","Critical"][i%3],"test_date":(now()-timedelta(days=i)).isoformat(),"values":{"glucose":85+i,"cholesterol":160+i}})
    for i in range(45): insert("predictions",{"patient_id":patients[i]["id"],"disease":diseases[i%5],"probability":35+(i*7)%60,"confidence":82+(i%15),"risk_level":["LOW","MEDIUM","HIGH"][i%3],"model_version":"demo-1.0","timestamp":now().isoformat(),"disclaimer":True})

@app.get("/health")
def health(): return {"status":"ok","database":"mongodb" if db is not None else "demo-memory"}
@app.post("/auth/login")
def login(body: Login):
    user=next((u for u in find("users") if u["email"]==body.email),None)
    if not user or not pwd.verify(body.password,user["password_hash"]): raise HTTPException(401,"Incorrect email or password")
    token=jwt.encode({"sub":user["id"],"email":user["email"],"name":user["name"],"role":user["role"],"exp":now()+timedelta(hours=12)},SECRET,algorithm="HS256")
    audit(user,"User Login","Authentication")
    return {"access_token":token,"token_type":"bearer","user":{k:user[k] for k in ["id","name","email","role"]}}
@app.post("/auth/register")
def register(body:Register, user=Depends(require("ADMIN"))):
    if body.role not in ROLES: raise HTTPException(422,"Invalid role")
    if any(u["email"]==body.email for u in find("users")): raise HTTPException(409,"Email is already registered")
    result=insert("users",{"name":body.name,"email":str(body.email),"role":body.role,"password_hash":pwd.hash(body.password)})
    audit(user,"User Created","Users",body.email); return {"id":result["id"],"message":"User created"}
@app.get("/auth/me")
def me(user=Depends(require())): return user

COLLECTIONS={"patients":"patients","doctors":"doctors","appointments":"appointments","admissions":"admissions","diagnoses":"diagnoses","lab-reports":"lab_reports","medicines":"medicines","prescriptions":"prescriptions","predictions":"predictions","notifications":"notifications","audit-logs":"audit_logs"}
@app.get("/records/{resource}")
def list_records(resource:str, q:Optional[str]=None, page:int=1, limit:int=20, user=Depends(require())):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown resource")
    col=COLLECTIONS[resource]; rows=find(col)
    if q:
        key=q.lower(); rows=[r for r in rows if key in str(r).lower()]
    return {"items":rows[(page-1)*limit:page*limit],"total":len(rows),"page":page}
@app.post("/records/{resource}")
def create_record(resource:str, body:Record, user=Depends(require("ADMIN","DOCTOR","RECEPTIONIST","LAB TECHNICIAN","PHARMACIST"))):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown resource")
    role_rules={"patients":{"ADMIN","RECEPTIONIST"},"doctors":{"ADMIN"},"appointments":{"ADMIN","RECEPTIONIST","DOCTOR"},"lab-reports":{"ADMIN","LAB TECHNICIAN"},"medicines":{"ADMIN","PHARMACIST"},"diagnoses":{"ADMIN","DOCTOR"},"prescriptions":{"ADMIN","DOCTOR"}}
    if resource in role_rules and user["role"] not in role_rules[resource]: raise HTTPException(403,"Role cannot create this record")
    rec=insert(COLLECTIONS[resource],body.data); audit(user,"Created",resource,rec.get("id","")); return rec
@app.get("/records/{resource}/{id}")
def get_record(resource:str,id:str,user=Depends(require())):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown resource")
    rec=one(COLLECTIONS[resource],id)
    if not rec: raise HTTPException(404,"Record not found")
    return rec
@app.put("/records/{resource}/{id}")
def update_record(resource:str,id:str,body:Record,user=Depends(require())):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown resource")
    result=update(COLLECTIONS[resource],id,body.data); audit(user,"Updated",resource,id); return result
@app.delete("/records/{resource}/{id}")
def delete_record(resource:str,id:str,user=Depends(require("ADMIN"))):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown resource")
    remove(COLLECTIONS[resource],id); audit(user,"Deleted",resource,id); return {"message":"Deleted"}

@app.get("/analytics/dashboard")
def dashboard(user=Depends(require())):
    patients=find("patients"); appts=find("appointments"); meds=find("medicines"); preds=find("predictions")
    return {"kpis":{"total_patients":len(patients),"total_doctors":len(find("doctors")),"appointments_today":sum(a.get("appointment_date","")[:10]==now().date().isoformat() for a in appts),"active_admissions":len([x for x in find("admissions") if x.get("status")!="Discharged"])},"critical_patients":sum(p.get("risk_level")=="HIGH" for p in patients),"low_stock":sum(m.get("quantity",0)<=m.get("minimum_stock_level",0) for m in meds),"high_risk_predictions":sum(p.get("risk_level")=="HIGH" for p in preds),"growth":[{"month":m,"patients":70+i*8,"admissions":14+i*2} for i,m in enumerate(["Mar","Apr","May","Jun","Jul","Aug"])],"diseases":[{"name":d,"value":sum(d in str(p.get("existing_diseases")) for p in patients)} for d in ["Diabetes","Hypertension","Heart Disease","Asthma","Kidney Disease"]],"recent_patients":patients[:5],"upcoming_appointments":[a for a in appts if a.get("status") in ["Scheduled","Confirmed"]][:5],"recent_predictions":preds[:5]}
@app.post("/predictions/generate")
def prediction(body:Prediction,user=Depends(require("ADMIN","DOCTOR"))):
    if not one("patients",body.patient_id): raise HTTPException(404,"Patient not found")
    numeric=[float(v) for v in body.inputs.values() if str(v).replace('.','',1).isdigit()]
    score=min(96,max(4,round(25+(sum(numeric)/max(1,len(numeric)))%60+random.random()*12)))
    level="HIGH" if score>=70 else "MEDIUM" if score>=40 else "LOW"
    rec=insert("predictions",{"patient_id":body.patient_id,"disease":body.disease,"inputs":body.inputs,"probability":score,"confidence":round(78+random.random()*18,1),"risk_level":level,"model_version":"research-demo-1.0","timestamp":now().isoformat(),"disclaimer":True})
    if level=="HIGH": insert("notifications",{"title":"High risk estimate","message":f"{body.disease} risk estimate requires clinician review.","read":False,"type":"warning"})
    audit(user,"Prediction Generated","Predictions",body.disease); return rec
@app.post("/etl/upload")
async def etl_upload(file:UploadFile=File(...),user=Depends(require("ADMIN"))):
    if not file.filename or file.filename.rsplit(".",1)[-1].lower() not in {"csv","json","xlsx","xls"}: raise HTTPException(422,"Only CSV, JSON, or Excel files are accepted")
    raw=await file.read()
    try:
        ext=file.filename.rsplit(".",1)[-1].lower(); df=pd.read_csv(io.BytesIO(raw)) if ext=="csv" else pd.read_json(io.BytesIO(raw)) if ext=="json" else pd.read_excel(io.BytesIO(raw))
    except Exception: raise HTTPException(422,"Could not parse dataset")
    original=len(df); duplicates=int(df.duplicated().sum()); missing=int(df.isna().sum().sum()); df=df.drop_duplicates(); df.columns=[str(c).strip().lower().replace(" ","_") for c in df.columns]; df=df.fillna("Unknown")
    job=insert("etl_jobs",{"job_id":f"ETL-{secrets.token_hex(4).upper()}","dataset":file.filename,"file_type":ext,"original_rows":original,"columns":len(df.columns),"duplicates_removed":duplicates,"missing_values_fixed":missing,"rows_processed":len(df),"status":"Completed","start_time":now().isoformat(),"end_time":now().isoformat()})
    if db is not None and not df.empty: db["analytics"].insert_many(df.replace({np.nan:None}).to_dict("records"))
    audit(user,"ETL Processed","ETL",file.filename); return job
@app.get("/reports/{resource}.csv")
def export_csv(resource:str,user=Depends(require())):
    if resource not in COLLECTIONS: raise HTTPException(404,"Unknown report")
    rows=find(COLLECTIONS[resource]); output=io.StringIO();
    if rows: csv.DictWriter(output,fieldnames=sorted({k for x in rows for k in x}),extrasaction="ignore").writeheader(); csv.DictWriter(output,fieldnames=sorted({k for x in rows for k in x}),extrasaction="ignore").writerows(rows)
    return StreamingResponse(iter([output.getvalue()]),media_type="text/csv",headers={"Content-Disposition":f"attachment; filename={resource}-report.csv"})
@app.get("/audit-logs")
def logs(user=Depends(require("ADMIN"))): return find("audit_logs")[:100]
