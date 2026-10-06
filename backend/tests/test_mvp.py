import io, zipfile
from pathlib import Path
from fastapi.testclient import TestClient
from PIL import Image
from lxml import etree
import pytest
import app.main as main
from app.main import app, Base, Subject, Profile
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

@pytest.fixture
def client(tmp_path,monkeypatch):
    test_data=tmp_path/"data";test_data.mkdir()
    test_db=create_engine(f"sqlite:///{(tmp_path/'test.sqlite3').as_posix()}",connect_args={"check_same_thread":False})
    monkeypatch.setattr(main,"DB",test_db);monkeypatch.setattr(main,"DATA",test_data)
    Base.metadata.create_all(test_db)
    with Session(test_db) as s:
        s.add(Subject(name="Тестовый предмет",teacher="Преподаватель тестовый"))
        s.add(Profile(id=1,student="Студент тестовый",specialty="Тестовая специальность",group_name="ТЕСТ-1",city="Город тестовый"));s.commit()
    with TestClient(app) as test_client:yield test_client
    test_db.dispose()

def png(color):
    im=Image.new("RGB",(32,24),color)
    b=io.BytesIO();im.save(b,format="PNG");return b.getvalue()

def test_end_to_end_export_and_figure_order(client):
    sid=client.get('/api/subjects').json()[0]['id']
    r=client.post('/api/reports').json();rid=r['id'];tid=r['tasks'][0]['id'];step1=r['tasks'][0]['steps'][0]['id']
    assert client.patch(f'/api/reports/{rid}',json={"subject_id":sid,"work_number":"88","year":"2026","goal":"Изучить предмет","equipment":"Компьютер","auto_conclusion":True,"conclusion":""}).status_code==200
    assert client.patch(f'/api/tasks/{tid}',json={"text":"Первое задание"}).status_code==200
    assert client.patch(f'/api/steps/{step1}',json={"text":"Первый шаг"}).status_code==200
    step2=client.post(f'/api/tasks/{tid}/steps',json={}).json()['id']
    client.patch(f'/api/steps/{step2}',json={"text":"Второй шаг"})
    f1=client.post(f'/api/reports/{rid}/files',files={"file":("screen-a.png",png("red"),"image/png")}).json()
    f2=client.post(f'/api/reports/{rid}/files',files={"file":("screen-b.png",png("blue"),"image/png")}).json()
    t2=client.post(f'/api/reports/{rid}/tasks',json={}).json()['id']
    s3=client.get(f'/api/reports/{rid}').json()['tasks'][1]['steps'][0]['id']
    client.patch(f'/api/tasks/{t2}',json={"text":"Второе задание"});client.patch(f'/api/steps/{s3}',json={"text":"Третий шаг"})
    f3=client.post(f'/api/reports/{rid}/files',files={"file":("screen-c.png",png("green"),"image/png")}).json()
    client.post(f'/api/steps/{step1}/attachments',json={"file_id":f1['id']});client.post(f'/api/steps/{step2}/attachments',json={"file_id":f2['id']})
    client.post(f'/api/steps/{s3}/attachments',json={"file_id":f3['id']})
    assert client.get(f'/api/reports/{rid}').json()['figure_map']=={f1['id']:1,f2['id']:2,f3['id']:3}
    assert client.delete(f'/api/steps/{step1}/attachments/{f1["id"]}').status_code==204
    assert client.get(f'/api/files/{f1["id"]}/content').status_code==200
    client.post(f'/api/steps/{step1}/attachments',json={"file_id":f1['id']})
    assert client.post('/api/tasks/reorder',json={"ids":[t2,tid]}).status_code==200
    assert client.get(f'/api/reports/{rid}').json()['figure_map']=={f3['id']:1,f1['id']:2,f2['id']:3}
    # Reordering step records recalculates figures from their new first appearance.
    assert client.post('/api/steps/reorder',json={"ids":[step2,step1]}).status_code==200
    doc=client.get(f'/api/reports/{rid}').json();assert doc['figure_map']=={f3['id']:1,f2['id']:2,f1['id']:3}
    assert client.get(f'/api/reports/{rid}/validation').json()['valid'] is True
    out=client.post(f'/api/reports/{rid}/export/odt');assert out.status_code==200
    z=zipfile.ZipFile(io.BytesIO(out.content));assert z.namelist()[0]=='mimetype';assert z.getinfo('mimetype').compress_type==zipfile.ZIP_STORED
    xml=etree.fromstring(z.read('content.xml'))
    ns={'office':'urn:oasis:names:tc:opendocument:xmlns:office:1.0','text':'urn:oasis:names:tc:opendocument:xmlns:text:1.0','style':'urn:oasis:names:tc:opendocument:xmlns:style:1.0','fo':'urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0'}
    paragraphs=xml.xpath('//text:p',namespaces=ns)
    get_text=lambda p: ''.join(p.itertext()).strip()
    with zipfile.ZipFile(main.TEMPLATE) as source:
        source_xml=etree.fromstring(source.read('content.xml'))
    source_body=source_xml.find('.//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}body/{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text')
    exported_body=xml.find('.//{urn:oasis:names:tc:opendocument:xmlns:office:1.0}body/{urn:oasis:names:tc:opendocument:xmlns:office:1.0}text')
    source_cover=source_body.xpath('./text:p',namespaces=ns)
    exported_cover=exported_body.xpath('./text:p',namespaces=ns)
    source_p12=next(i for i,p in enumerate(source_cover) if p.get('{%s}style-name'%ns['text'])=='P12')
    exported_p12=next(i for i,p in enumerate(exported_cover) if p.get('{%s}style-name'%ns['text'])=='P12')
    assert source_p12==exported_p12
    assert [p.get('{%s}style-name'%ns['text']) for p in source_cover[:source_p12+1]]==[p.get('{%s}style-name'%ns['text']) for p in exported_cover[:exported_p12+1]]
    exported_p13=next(i for i,p in enumerate(exported_cover) if p.get('{%s}style-name'%ns['text'])=='P13')
    first_body_heading=next(i for i,p in enumerate(exported_cover) if p.get('{%s}style-name'%ns['text'])=='P14')
    assert 0<=exported_p13-exported_p12-1<=8
    assert exported_p13<first_body_heading
    for old,new in zip(source_cover[:source_p12+1],exported_cover[:exported_p12+1]):
        assert old.get('{%s}style-name'%ns['text'])==new.get('{%s}style-name'%ns['text'])
        assert [x.get('{%s}style-name'%ns['text']) for x in old.xpath('./text:span',namespaces=ns)]==[x.get('{%s}style-name'%ns['text']) for x in new.xpath('./text:span',namespaces=ns)]
    cover=next(p for p in paragraphs if get_text(p).startswith('ОТЧЁТ по практической'))
    assert cover.get('{%s}style-name'%ns['text'])=='P4'
    assert [x.get('{%s}style-name'%ns['text']) for x in cover.xpath('./text:span',namespaces=ns)]==['T2','T3']
    student_line=next(p for p in paragraphs if get_text(p).startswith('Выполнил(-а):'))
    assert get_text(student_line)=='Выполнил(-а): Студент тестовый.'
    styles={s.get('{%s}name'%ns['style']):s for s in xml.xpath('//office:automatic-styles/style:style',namespaces=ns)}
    heading=next(p for p in paragraphs if get_text(p)=='Цель работы')
    heading_style=styles[heading.get('{%s}style-name'%ns['text'])]
    heading_props=heading_style.find('{%s}paragraph-properties'%ns['style']);heading_text=heading_style.find('{%s}text-properties'%ns['style'])
    assert heading_props.get('{%s}text-align'%ns['fo'])=='start'
    assert heading_text.get('{%s}font-size'%ns['fo'])=='14pt'
    ordinary=next(p for p in paragraphs if get_text(p).startswith('1. Третий шаг'))
    body_style=styles[ordinary.get('{%s}style-name'%ns['text'])]
    assert body_style.find('{%s}text-properties'%ns['style']).get('{%s}font-size'%ns['fo'])=='12pt'
    assert 'content.xml' in z.namelist() and len([n for n in z.namelist() if n.startswith('Pictures/')])==3
    serialized=etree.tostring(xml,encoding='utf-8');assert all(f'Рис {n}'.encode() in serialized for n in (1,2,3))

def test_export_rejects_invalid_report(client):
    r=client.post('/api/reports').json();res=client.post(f"/api/reports/{r['id']}/export/odt")
    assert res.status_code==422 and 'Отчёт не готов' in res.json()['detail']['message']
