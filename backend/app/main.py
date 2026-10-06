from __future__ import annotations

import mimetypes
import os
import shutil
import uuid
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File as UploadFile, HTTPException, Response, UploadFile as IncomingFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship
from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
DATA = Path(os.environ.get("APP_DATA_DIR", str(ROOT / "data"))).resolve()
TEMPLATE = ROOT / "templates" / "report-template.odt"
FRONTEND_DIST = ROOT / "frontend" / "dist"
DB = create_engine(f"sqlite:///{(DATA / 'reports.sqlite3').as_posix()}", connect_args={"check_same_thread": False})
DATA.mkdir(exist_ok=True)

class Base(DeclarativeBase): pass

class Subject(Base):
    __tablename__ = "subjects"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String, unique=True)
    teacher: Mapped[str] = mapped_column(String, default="")

class Profile(Base):
    __tablename__ = "profile"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    student: Mapped[str] = mapped_column(String, default="")
    specialty: Mapped[str] = mapped_column(String, default="")
    group_name: Mapped[str] = mapped_column(String, default="")
    teacher: Mapped[str] = mapped_column(String, default="")
    city: Mapped[str] = mapped_column(String, default="")

class Report(Base):
    __tablename__ = "reports"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String, default="")
    subject_id: Mapped[str | None] = mapped_column(ForeignKey("subjects.id"), nullable=True)
    work_number: Mapped[str] = mapped_column(String, default="")
    year: Mapped[str] = mapped_column(String, default=lambda: str(datetime.now().year))
    goal: Mapped[str] = mapped_column(Text, default="")
    equipment: Mapped[str] = mapped_column(Text, default="Компьютер с ОС Windows 11")
    auto_conclusion: Mapped[bool] = mapped_column(Boolean, default=True)
    conclusion: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    tasks: Mapped[list[Task]] = relationship(back_populates="report", cascade="all, delete-orphan", order_by="Task.position")
    files: Mapped[list[File]] = relationship(back_populates="report", cascade="all, delete-orphan", order_by="File.created_at")

class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[Report] = relationship(back_populates="tasks")
    steps: Mapped[list[Step]] = relationship(back_populates="task", cascade="all, delete-orphan", order_by="Step.position")

class Step(Base):
    __tablename__ = "steps"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    text: Mapped[str] = mapped_column(Text, default="")
    position: Mapped[int] = mapped_column(Integer, default=0)
    task: Mapped[Task] = relationship(back_populates="steps")
    attachments: Mapped[list[StepAttachment]] = relationship(back_populates="step", cascade="all, delete-orphan", order_by="StepAttachment.position")

class File(Base):
    __tablename__ = "files"
    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    report_id: Mapped[str] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"))
    original_name: Mapped[str] = mapped_column(String)
    stored_name: Mapped[str] = mapped_column(String, unique=True)
    mime_type: Mapped[str] = mapped_column(String)
    size: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    report: Mapped[Report] = relationship(back_populates="files")

class StepAttachment(Base):
    __tablename__ = "step_attachments"
    step_id: Mapped[str] = mapped_column(ForeignKey("steps.id", ondelete="CASCADE"), primary_key=True)
    file_id: Mapped[str] = mapped_column(ForeignKey("files.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    step: Mapped[Step] = relationship(back_populates="attachments")
    file: Mapped[File] = relationship()

DATA.mkdir(parents=True, exist_ok=True)
Base.metadata.create_all(DB)
with Session(DB) as _seed:
    if not _seed.scalar(select(Subject)):
        _seed.add_all([Subject(name="Операционные системы и среды"), Subject(name="Технологии обработки информации")])
        _seed.commit()
    if not _seed.get(Profile, 1):
        _seed.add(Profile(id=1,
            student=os.getenv("REPORT_STUDENT", ""),
            specialty=os.getenv("REPORT_SPECIALTY", ""),
            group_name=os.getenv("REPORT_GROUP", ""),
            teacher=os.getenv("REPORT_TEACHER", ""),
            city=os.getenv("REPORT_CITY", "")))
        _seed.commit()
app = FastAPI(title="Практические работы")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])

class SubjectInput(BaseModel): name: str; teacher: str = ""
class ReportInput(BaseModel): subject_id: str | None = None; work_number: str = ""; year: str = str(datetime.now().year); goal: str = ""; equipment: str = "Компьютер с ОС Windows 11"; auto_conclusion: bool = True; conclusion: str = ""; title: str = ""
class TaskInput(BaseModel): text: str = ""
class StepInput(BaseModel): text: str = ""
class OrderInput(BaseModel): ids: list[str]
class AttachInput(BaseModel): file_id: str

def get_report(s: Session, rid: str) -> Report:
    r=s.get(Report,rid)
    if not r: raise HTTPException(404,"Отчёт не найден")
    return r

def figure_map(r: Report) -> dict[str,int]:
    out={}
    for t in r.tasks:
        for st in t.steps:
            for a in st.attachments:
                if a.file and a.file.id not in out: out[a.file.id]=len(out)+1
    return out

def report_json(r: Report, s: Session) -> dict[str,Any]:
    subject=s.get(Subject,r.subject_id) if r.subject_id else None
    figs=figure_map(r)
    return {"id":r.id,"title":r.title,"subject_id":r.subject_id,"subject":subject.name if subject else "","teacher":subject.teacher if subject else "","work_number":r.work_number,"year":r.year,"goal":r.goal,"equipment":r.equipment,"auto_conclusion":r.auto_conclusion,"conclusion":r.conclusion,"created_at":r.created_at.isoformat(),"updated_at":r.updated_at.isoformat(),"figure_map":figs,"tasks":[{"id":t.id,"text":t.text,"position":t.position,"steps":[{"id":st.id,"text":st.text,"position":st.position,"attachments":[{"id":a.file.id,"name":a.file.original_name,"url":f"/api/files/{a.file.id}/content","figure_number":figs.get(a.file.id)} for a in st.attachments if a.file]} for st in t.steps]} for t in r.tasks],"files":[{"id":f.id,"name":f.original_name,"mime_type":f.mime_type,"size":f.size,"created_at":f.created_at.isoformat(),"url":f"/api/files/{f.id}/content","figure_number":figs.get(f.id)} for f in r.files]}

@app.get("/api/subjects")
def subjects():
    with Session(DB) as s: return [{"id":x.id,"name":x.name,"teacher":x.teacher} for x in s.scalars(select(Subject).order_by(Subject.name))]
@app.post("/api/subjects")
def add_subject(data:SubjectInput):
    with Session(DB) as s:
        x=Subject(name=data.name.strip(),teacher=data.teacher.strip());s.add(x);s.commit();return {"id":x.id,"name":x.name,"teacher":x.teacher}
@app.patch("/api/subjects/{sid}")
def edit_subject(sid:str,data:SubjectInput):
    with Session(DB) as s:
        x=s.get(Subject,sid)
        if not x: raise HTTPException(404,"Предмет не найден")
        x.name=data.name.strip();x.teacher=data.teacher.strip();s.commit();return {"id":x.id,"name":x.name,"teacher":x.teacher}
@app.delete("/api/subjects/{sid}",status_code=204)
def del_subject(sid:str):
    with Session(DB) as s:
        x=s.get(Subject,sid)
        if not x: raise HTTPException(404,"Предмет не найден")
        if s.scalar(select(Report).where(Report.subject_id==sid)): raise HTTPException(409,"Сначала измените предмет в связанных отчётах")
        s.delete(x);s.commit();return Response(status_code=204)

@app.get("/api/reports")
def reports():
    with Session(DB) as s:
        rows=s.scalars(select(Report).order_by(Report.updated_at.desc())).all()
        return [{"id":r.id,"work_number":r.work_number,"year":r.year,"subject":s.get(Subject,r.subject_id).name if r.subject_id and s.get(Subject,r.subject_id) else "—","updated_at":r.updated_at.isoformat(),"completion":completion(r)} for r in rows]
def completion(r:Report):
    checks=[bool(r.subject_id),bool(r.work_number.strip()),bool(r.year.strip()),bool(r.goal.strip()),bool(r.equipment.strip()),bool(r.tasks) and all(t.text.strip() and t.steps and all(st.text.strip() for st in t.steps) for t in r.tasks),bool(r.auto_conclusion or r.conclusion.strip())]
    return sum(checks),len(checks)
@app.post("/api/reports")
def create_report():
    with Session(DB) as s:
        r=Report();s.add(r);s.flush();t=Task(report_id=r.id,position=0);s.add(t);s.flush();s.add(Step(task_id=t.id,position=0));s.commit();s.refresh(r);return report_json(r,s)
@app.get("/api/reports/{rid}")
def read_report(rid:str):
    with Session(DB) as s:return report_json(get_report(s,rid),s)
@app.patch("/api/reports/{rid}")
def patch_report(rid:str,data:ReportInput):
    with Session(DB) as s:
        r=get_report(s,rid)
        if data.subject_id and not s.get(Subject,data.subject_id): raise HTTPException(400,"Предмет не найден")
        for k,v in data.model_dump().items():setattr(r,k,v)
        r.updated_at=datetime.utcnow();s.commit();s.refresh(r);return report_json(r,s)
@app.delete("/api/reports/{rid}",status_code=204)
def delete_report(rid:str):
    with Session(DB) as s:
        r=get_report(s,rid);folder=DATA/"reports"/rid;s.delete(r);s.commit();shutil.rmtree(folder,ignore_errors=True);return Response(status_code=204)

@app.post("/api/reports/{rid}/tasks")
def add_task(rid:str,data:TaskInput=TaskInput()):
    with Session(DB) as s:
        r=get_report(s,rid);t=Task(report_id=rid,text=data.text,position=len(r.tasks));s.add(t);s.flush();s.add(Step(task_id=t.id,position=0));r.updated_at=datetime.utcnow();s.commit();return {"id":t.id}
@app.patch("/api/tasks/{tid}")
def patch_task(tid:str,data:TaskInput):
    with Session(DB) as s:
        t=s.get(Task,tid)
        if not t:raise HTTPException(404,"Задание не найдено")
        t.text=data.text;t.report.updated_at=datetime.utcnow();s.commit();return {"ok":True}
@app.delete("/api/tasks/{tid}",status_code=204)
def del_task(tid:str):
    with Session(DB) as s:
        t=s.get(Task,tid)
        if not t:raise HTTPException(404,"Задание не найдено")
        rid=t.report_id;pos=t.position;s.delete(t);s.flush()
        for i,x in enumerate(s.scalars(select(Task).where(Task.report_id==rid).order_by(Task.position)).all()):x.position=i
        s.get(Report,rid).updated_at=datetime.utcnow();s.commit();return Response(status_code=204)
@app.post("/api/tasks/reorder")
def reorder_tasks(data:OrderInput):
    with Session(DB) as s:
        items=[s.get(Task,i) for i in data.ids]
        if any(x is None for x in items) or len({x.report_id for x in items})>1:raise HTTPException(400,"Неверный порядок заданий")
        for i,x in enumerate(items):x.position=i
        if items:items[0].report.updated_at=datetime.utcnow()
        s.commit();return {"ok":True}
@app.post("/api/tasks/{tid}/steps")
def add_step(tid:str,data:StepInput=StepInput()):
    with Session(DB) as s:
        t=s.get(Task,tid)
        if not t:raise HTTPException(404,"Задание не найдено")
        st=Step(task_id=tid,text=data.text,position=len(t.steps));s.add(st);t.report.updated_at=datetime.utcnow();s.commit();return {"id":st.id}
@app.patch("/api/steps/{sid}")
def patch_step(sid:str,data:StepInput):
    with Session(DB) as s:
        st=s.get(Step,sid)
        if not st:raise HTTPException(404,"Шаг не найден")
        st.text=data.text;st.task.report.updated_at=datetime.utcnow();s.commit();return {"ok":True}
@app.delete("/api/steps/{sid}",status_code=204)
def del_step(sid:str):
    with Session(DB) as s:
        st=s.get(Step,sid)
        if not st:raise HTTPException(404,"Шаг не найден")
        tid=st.task_id;rid=st.task.report_id;s.delete(st);s.flush()
        for i,x in enumerate(s.scalars(select(Step).where(Step.task_id==tid).order_by(Step.position)).all()):x.position=i
        s.get(Report,rid).updated_at=datetime.utcnow();s.commit();return Response(status_code=204)
@app.post("/api/steps/reorder")
def reorder_steps(data:OrderInput):
    with Session(DB) as s:
        items=[s.get(Step,i) for i in data.ids]
        if any(x is None for x in items) or len({x.task_id for x in items})>1:raise HTTPException(400,"Неверный порядок шагов")
        for i,x in enumerate(items):x.position=i
        if items:items[0].task.report.updated_at=datetime.utcnow()
        s.commit();return {"ok":True}

@app.post("/api/reports/{rid}/files")
async def upload(rid:str,file:IncomingFile=UploadFile(...)):
    with Session(DB) as s:
        r=get_report(s,rid);name=Path(file.filename or "screenshot.png").name;ext=Path(name).suffix.lower()
        allowed={".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",".webp":"image/webp"}
        if ext not in allowed or (file.content_type and file.content_type not in allowed.values()):raise HTTPException(415,"Поддерживаются PNG, JPG и WebP")
        content=await file.read(30*1024*1024+1)
        if not content or len(content)>30*1024*1024:raise HTTPException(413,"Файл должен быть до 30 МБ")
        if not content.startswith((b'\x89PNG\r\n\x1a\n',b'\xff\xd8\xff',b'RIFF')):raise HTTPException(415,"Содержимое не похоже на изображение")
        fid=str(uuid.uuid4());stored=fid+ext;folder=DATA/"reports"/rid/"files";folder.mkdir(parents=True,exist_ok=True);path=folder/stored
        path.write_bytes(content)
        try:
            f=File(id=fid,report_id=rid,original_name=name,stored_name=stored,mime_type=allowed[ext],size=len(content));s.add(f);r.updated_at=datetime.utcnow();s.commit()
        except Exception:
            path.unlink(missing_ok=True);raise
        return {"id":fid,"name":name,"mime_type":f.mime_type,"size":f.size,"created_at":f.created_at.isoformat(),"url":f"/api/files/{fid}/content"}
@app.get("/api/files/{fid}/content")
def content(fid:str):
    with Session(DB) as s:
        f=s.get(File,fid)
        if not f:raise HTTPException(404,"Файл не найден")
        path=DATA/"reports"/f.report_id/"files"/f.stored_name
        if not path.is_file():raise HTTPException(404,"Файл отсутствует на диске")
        return FileResponse(path,media_type=f.mime_type)
@app.delete("/api/files/{fid}")
def delete_file(fid:str):
    with Session(DB) as s:
        f=s.get(File,fid)
        if not f:raise HTTPException(404,"Файл не найден")
        used=s.scalar(select(StepAttachment).where(StepAttachment.file_id==fid))
        if used:raise HTTPException(409,"Сначала открепите изображение от шагов")
        path=DATA/"reports"/f.report_id/"files"/f.stored_name;s.delete(f);s.commit();path.unlink(missing_ok=True);return {"ok":True}
@app.post("/api/steps/{sid}/attachments")
def attach(sid:str,data:AttachInput):
    with Session(DB) as s:
        st=s.get(Step,sid);f=s.get(File,data.file_id)
        if not st or not f:raise HTTPException(404,"Шаг или файл не найден")
        if st.task.report_id!=f.report_id:raise HTTPException(400,"Файл относится к другому отчёту")
        if not s.get(StepAttachment,(sid,f.id)):s.add(StepAttachment(step_id=sid,file_id=f.id,position=len(st.attachments)))
        st.task.report.updated_at=datetime.utcnow();s.commit();return {"ok":True}
@app.delete("/api/steps/{sid}/attachments/{fid}",status_code=204)
def detach(sid:str,fid:str):
    with Session(DB) as s:
        a=s.get(StepAttachment,(sid,fid))
        if not a:raise HTTPException(404,"Связь не найдена")
        a.step.task.report.updated_at=datetime.utcnow();s.delete(a);s.commit();return Response(status_code=204)

def validate_report(r:Report) -> list[str]:
    errors=[]
    if not r.subject_id:errors.append("Не выбран предмет")
    if not r.work_number.strip():errors.append("Не указан номер практической работы")
    if not r.year.strip():errors.append("Не указан год")
    if not r.goal.strip():errors.append("Не заполнена цель работы")
    if not r.equipment.strip():errors.append("Не заполнено оборудование и ПО")
    if not r.tasks:errors.append("Добавьте хотя бы одно задание")
    for i,t in enumerate(r.tasks,1):
        if not t.text.strip():errors.append(f"Задание {i}: не заполнен текст")
        if not t.steps:errors.append(f"Задание {i}: добавьте хотя бы один шаг")
        for j,st in enumerate(t.steps,1):
            if not st.text.strip():errors.append(f"Задание {i}: не заполнен пункт {j}")
            for a in st.attachments:
                if not a.file or not (DATA/"reports"/r.id/"files"/a.file.stored_name).is_file():errors.append(f"Задание {i}, пункт {j}: прикреплённый файл отсутствует")
    if not r.auto_conclusion and not r.conclusion.strip():errors.append("Не заполнен вывод")
    return errors
@app.get("/api/reports/{rid}/validation")
def validation(rid:str):
    with Session(DB) as s:
        r=get_report(s,rid);return {"valid":not validate_report(r),"errors":validate_report(r)}

NS={"office":"urn:oasis:names:tc:opendocument:xmlns:office:1.0","text":"urn:oasis:names:tc:opendocument:xmlns:text:1.0","draw":"urn:oasis:names:tc:opendocument:xmlns:drawing:1.0","xlink":"http://www.w3.org/1999/xlink","svg":"urn:oasis:names:tc:opendocument:xmlns:svg-compatible:1.0","style":"urn:oasis:names:tc:opendocument:xmlns:style:1.0"}
NS["fo"]="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0"
def export_report_to_odt(r:Report,subject:Subject, path:Path):
    with zipfile.ZipFile(TEMPLATE) as zin:
        content=etree.fromstring(zin.read("content.xml"));body=content.find(".//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}body/{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text")
        paras=body.xpath(".//text:p",namespaces=NS)
        samples={}
        for p in paras:
            sty=p.get("{%s}style-name"%NS["text"])
            if sty and sty not in samples:samples[sty]=p
        automatic=content.find("{%s}automatic-styles"%NS["office"])
        def template_style(name):
            matches=automatic.xpath("./style:style[@style:name=$name]",namespaces=NS,name=name)
            if not matches:
                raise ValueError(f"В шаблоне отсутствует стиль абзаца {name}")
            return matches[0]
        def set_template_style(name,size=None,align=None,remove_page_break=False,parent=None,weight=None):
            """Adjust an existing template style without breaking its spacing/inheritance."""
            style_el=template_style(name)
            # Heading_3 was attached only to the conclusion heading in the source
            # document. Reparent it to body text so Writer/Word don't treat just
            # that paragraph as a collapsible outline heading.
            if parent is not None:style_el.set("{%s}parent-style-name"%NS["style"],parent)
            style_el.attrib.pop("{%s}default-outline-level"%NS["style"],None)
            pp=style_el.find("{%s}paragraph-properties"%NS["style"])
            if pp is None and align is not None:
                pp=etree.SubElement(style_el,"{%s}paragraph-properties"%NS["style"])
            if pp is not None:
                if align is not None:pp.set("{%s}text-align"%NS["fo"],align)
                if remove_page_break:pp.attrib.pop("{%s}break-before"%NS["fo"],None)
            if size is not None:
                tp=style_el.find("{%s}text-properties"%NS["style"])
                if tp is None:tp=etree.SubElement(style_el,"{%s}text-properties"%NS["style"])
                tp.set("{%s}font-size"%NS["fo"],size)
                tp.set("{%s}font-size-asian"%NS["style"],size)
                tp.set("{%s}font-size-complex"%NS["style"],size)
            if weight is not None:
                tp=style_el.find("{%s}text-properties"%NS["style"])
                if tp is None:tp=etree.SubElement(style_el,"{%s}text-properties"%NS["style"])
                tp.set("{%s}font-weight"%NS["fo"],weight)
                tp.set("{%s}font-weight-asian"%NS["style"],weight)
                tp.set("{%s}font-weight-complex"%NS["style"],weight)
        # Keep the template's paragraph styles, spacing and intentional page breaks.
        # The cover page styles are deliberately untouched.
        for style_name in ("P14","P18","P19","P23"):
            set_template_style(style_name,"14pt","start",parent="Text_20_body",weight="bold")
        for style_name in ("P15","P16","P17","P20","P24"):
            set_template_style(style_name,"12pt")
        # P26 is used for appendix images and captions. Keep it centered but remove
        # its source page break so every image and its caption can stay together.
        set_template_style("P26","12pt","center",remove_page_break=True)
        def para(parent,text="",size="12pt",align="start",label="Body"):
            p=etree.fromstring(etree.tostring(samples.get(parent,samples.get("P20"))));p.clear()
            p.set("{%s}style-name"%NS["text"],parent);p.text=text
            return p
        def replace_title_runs(p,run_texts):
            spans=p.xpath(".//text:span",namespaces=NS)
            if not spans:
                span=etree.SubElement(p,"{%s}span"%NS["text"]);span.set("{%s}style-name"%NS["text"],"T1");spans=[span]
            for i,span in enumerate(spans):
                value=run_texts[i] if i<len(run_texts) else ""
                if value is None:continue
                for child in list(span):span.remove(child)
                span.text=value
            return p
        # Copy the complete source cover verbatim, including spacer paragraphs
        # that position the student block and put the city/year at the page foot.
        # Replace only the variable text runs; preserve each template style/span.
        cover=[]
        with Session(DB) as profile_db:
            profile=profile_db.get(Profile,1)
            identity=(profile.student,profile.specialty,profile.group_name,subject.teacher or profile.teacher,profile.city) if profile else ("","","",subject.teacher or "","")
        cover_styles={
            "P4":["ОТЧЁТ по практической работе № ",r.work_number],
            "P6":["«",subject.name.upper(),"»"],
            "P9":["Выполнил(-а):",None,identity[0].rstrip("."),"."],
            "P10":["специальность:",None,f"«{identity[1]}","»,"],
            "P11":["группа:",f" {identity[2]}"],
            "P12":["Руководитель:",None,identity[3]],
            "P13":[f"{identity[4]} ",r.year[:2],r.year[2:]],
        }
        for el in list(body):
            if el.tag=="{%s}p"%NS["text"] and el.get("{%s}style-name"%NS["text"])=="P14":break
            clone=etree.fromstring(etree.tostring(el));cover.append(clone)
            sty=clone.get("{%s}style-name"%NS["text"])
            if sty in cover_styles:
                replace_title_runs(clone,cover_styles[sty])
                del cover_styles[sty]
        if cover_styles:raise ValueError(f"В титульном листе шаблона отсутствуют поля: {', '.join(cover_styles)}")
        # The source cover reserves eight blank lines before the city/year. Long
        # subjects or student details can wrap and push P13 onto page two. Keep
        # some of the original lower-page spacing, but shrink it according to
        # the actual text lengths so the city/year stay on the cover page.
        line_limits={"P4":62,"P6":64,"P9":42,"P10":42,"P11":42,"P12":42,"P13":64}
        wrap_risk=0
        for sty,runs in {
            "P4":cover_styles.get("P4",["ОТЧЁТ по практической работе № ",r.work_number]),
            "P6":cover_styles.get("P6",["«",subject.name.upper(),"»"]),
            "P9":["Выполнил(-а):",identity[0]],
            "P10":["специальность:",identity[1]],
            "P11":["группа:",identity[2]],
            "P12":["Руководитель:",identity[3]],
            "P13":[identity[4],r.year],
        }.items():
            value=" ".join(str(run) for run in runs if run is not None)
            wrap_risk+=max(0,(len(value)-1)//line_limits[sty])
        trailing_budget=max(0,4-wrap_risk)
        city_index=next((i for i,p in enumerate(cover) if p.get("{%s}style-name"%NS["text"])=="P13"),None)
        student_index=next((i for i,p in enumerate(cover) if p.get("{%s}style-name"%NS["text"])=="P12"),-1)
        trailing_spacers=[i for i in range(student_index+1,city_index or len(cover))
                          if cover[i].tag=="{%s}p"%NS["text"]
                          and cover[i].get("{%s}style-name"%NS["text"]) in ("P2","P3")
                          and not "".join(cover[i].itertext()).strip()]
        for i in reversed(trailing_spacers[trailing_budget:]):
            cover.pop(i)
        out=list(cover)
        out += [para("P14","Цель работы","14pt",label="Heading"),para("P15",r.goal),para("P14","Оборудование и ПО","14pt",label="Heading"),para("P16",r.equipment),para("P14","Задания","14pt",label="Heading")]
        for i,t in enumerate(r.tasks,1):out.append(para("P17",f"{i}. {t.text}"))
        out += [para("P18","Ход работы","14pt",label="Heading")]
        figmap=figure_map(r); fileblobs={}
        for i,t in enumerate(r.tasks,1):
            out.append(para("P19",f"Задание {i}","14pt",label="Heading"))
            for j,st in enumerate(t.steps,1):
                ap=[a for a in st.attachments if a.file]
                nums=[figmap[a.file.id] for a in ap]
                suffix=f" (Рис {', '.join(map(str,nums))})" if nums else ""
                out.append(para("P20",f"{j}. {st.text}{suffix}"))
        out += [para("P23","Выводы","14pt",label="Heading"),para("P24",r.goal if r.auto_conclusion else r.conclusion),para("P14","Приложение","14pt",label="Heading")]
        for fnum,fid in enumerate(figmap,1):
            f=next(f for f in r.files if f.id==fid);src=DATA/"reports"/r.id/"files"/f.stored_name
            raw=src.read_bytes();ext=Path(f.stored_name).suffix.lower();image_name=f"Pictures/{fid}{ext}";fileblobs[image_name]=raw
            imagepara=para("P26")
            width=4; height=3
            try:
                from PIL import Image
                from io import BytesIO
                im=Image.open(BytesIO(raw));width,height=im.size
                factor=min(1.0, 6.0/width, 7.0/height);width*=factor;height*=factor
                width_in=f"{width/96:.2f}in";height_in=f"{height/96:.2f}in"
            except Exception:width_in="4.00in";height_in="3.00in"
            frame=etree.SubElement(imagepara,"{%s}frame"%NS["draw"]);frame.set("{%s}name"%NS["draw"],f"Figure{fnum}");frame.set("{%s}anchor-type"%NS["text"],"paragraph");frame.set("{%s}width"%NS["svg"],width_in);frame.set("{%s}height"%NS["svg"],height_in)
            img=etree.SubElement(frame,"{%s}image"%NS["draw"]);img.set("{%s}href"%NS["xlink"],image_name);img.set("{%s}type"%NS["xlink"],"simple");img.set("{%s}show"%NS["xlink"],"embed");img.set("{%s}actuate"%NS["xlink"],"onLoad")
            out += [imagepara,para("P26",f"Рис {fnum}","12pt",label="Caption")]
        for el in list(body):body.remove(el)
        for el in out:body.append(el)
        xml=etree.tostring(content,xml_declaration=True,encoding="UTF-8")
        # Update manifest so inserted images are registered in the ODT package.
        manifest=etree.fromstring(zin.read("META-INF/manifest.xml"));mns="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0"
        for name in fileblobs:
            entry=etree.SubElement(manifest,"{%s}file-entry"%mns);entry.set("{%s}full-path"%mns,name);entry.set("{%s}media-type"%mns,mimetypes.guess_type(name)[0] or "image/png")
        with zipfile.ZipFile(path,"w") as zout:
            zout.writestr("mimetype",zin.read("mimetype"),compress_type=zipfile.ZIP_STORED)
            for item in zin.infolist():
                if item.filename=="mimetype":continue
                if item.filename=="content.xml":zout.writestr(item,xml)
                elif item.filename=="META-INF/manifest.xml":zout.writestr(item,etree.tostring(manifest,xml_declaration=True,encoding="UTF-8"))
                elif not item.filename.startswith("Pictures/"):zout.writestr(item,zin.read(item.filename))
            for name,data in fileblobs.items():zout.writestr(name,data,compress_type=zipfile.ZIP_DEFLATED)

@app.post("/api/reports/{rid}/export/odt")
def export(rid:str):
    with Session(DB) as s:
        r=get_report(s,rid);errors=validate_report(r)
        if errors:raise HTTPException(422,detail={"message":"Отчёт не готов","errors":errors})
        subject=s.get(Subject,r.subject_id);folder=DATA/"exports";folder.mkdir(exist_ok=True);path=folder/f"Практическая работа №{r.work_number}.odt"
        export_report_to_odt(r,subject,path)
        return FileResponse(path,filename=path.name,media_type="application/vnd.oasis.opendocument.text")

@app.get("/api/profile")
def profile():
    with Session(DB) as s:
        p=s.get(Profile,1)
        return {"student":p.student,"specialty":p.specialty,"group_name":p.group_name,"teacher":p.teacher,"city":p.city}
@app.patch("/api/profile")
def patch_profile(data:dict[str,str]):
    with Session(DB) as s:
        p=s.get(Profile,1)
        for key in ("student","specialty","group_name","teacher","city"):
            if key in data:setattr(p,key,data[key].strip())
        s.commit();return {"student":p.student,"specialty":p.specialty,"group_name":p.group_name,"teacher":p.teacher,"city":p.city}

@app.get("/{path:path}", include_in_schema=False)
def frontend_app(path: str):
    # Serve the built React app in the single-container deployment. In dev,
    # Vite serves the UI and proxies /api to this process.
    if not FRONTEND_DIST.is_dir() or path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404)
    root=FRONTEND_DIST.resolve()
    candidate=(root/path).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return FileResponse(candidate)
    index=root/"index.html"
    if index.is_file():return FileResponse(index)
    raise HTTPException(status_code=404)
