#!/usr/local/bin/python3
# coding=utf-8

#exec(open('get_id.py',encoding='UTF-8').read())
from myjavdb import myjavdb as mj
from valbum import mydfcat
kkkmj=mj()
import aria2p
import json
from pathlib import Path
import requests
from playwright.sync_api import sync_playwright

p=sync_playwright().start()

cdp_browser = p.chromium.connect_over_cdp("http://localhost:9222")

ARIA2_SERVER='http://192.168.50.7'


aria2 = aria2p.API(
    aria2p.Client(
        host=ARIA2_SERVER,
        port=6800,
        secret=""
    )
)
actors_file=[]


from selenium import webdriver
import json
import urllib.request
import os,sys
import shutil
import re
from random import *
import random
import pandas as pd
import numpy as np
from valbum import valbum as va
from lxml import etree
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC  # 和下面WebDriverWait一起用的

from selenium.webdriver.support.wait import WebDriverWait


from random import randint
from time import sleep


maglink_fn=Path('./maglink_added.json')
if maglink_fn.is_file():
    df_maglink=pd.read_json(maglink_fn)
else:
    df_maglink=pd.DataFrame([],columns=['id','cast','date','title','maglink'])

delays=[10,1,3,7,2,0.2,18,3,6,15,5,0.5,0.1,1,6,4,2,8,12]

def my_delay():
    #sleep(random.random()*0)
    sleep(random.choice(delays))
    #pass

def add_txt_maglink(mag_link):
    fn=Path('w:/maglink_added.txt')
    with open(fn,'a',encoding='utf-8') as fa:
        fa.write(mag_link+'\n') 
    
def add_javdb_maglink(mag_link):
    global ARIA2_SERVER,df_maglink,aria2
    print('please echk if aria2 is up')
    ks=aria2.get_global_options()
    
    df_maglink.loc[len(df_maglink)]=mag_link
    
    avid_i=str(random.random())
    dl_path=Path("/volume1/aria2/_dl")/avid_i
    dl_path_pc=Path("w:/_dl")/avid_i
    if not os.path.exists(dl_path_pc):
        
        os.makedirs(dl_path_pc)
    old_dir=ks.dir
    
    ks.dir=str(dl_path).replace('\\','/')  # Path要先轉成str,不然aria2會看到最後多一個'/'的字元，目錄＋檔案時，有些可能會出問題
    try:
        download = aria2.add_magnet(mag_link,options=ks)
    except:
        print('magnet link is failed')
    ks.dir="/volume1/aria2/_dl"

    

if os.path.isfile(Path('w:/myjavdb.lock')):
    print('the file is locked, please wait')
    quit()
#os.system('touch myjavdb.lock')
Path('w:/myjavdb.lock').write_text('lock')

def add_myjavdb(items,album_img_link,rate,series,tags,actors,release):  #將資料存到myjavdb
    global id_list,df,javdb_fn
    for jid,jtitle in items:
        jjid=jid.strip().upper()
        if "Uncensored" in jjid:
            jjid=jjid[:-12]
        if jjid in id_list:
            print (jjid," already in my_javdb")
            break
        else:
            id_list=id_list+[jjid]
            jjtitle=jtitle.strip()
            
            #AV='見つかりませ女優の情報なし'
            if len(actors)==0:
                AV='見つかりませ女優の情報なし'
                actor='見つかりませ女優の情報なし'
                av_list=[AV,jjtitle,0,0,0,jjid,actor,album_img_link,rate,series,tags,actors,release]
                #print(len(df))
                df.loc[len(df)]=av_list  
                #print(len(df))
            for alink,actor in actors:
                if len(actors)>1:
                    AV='Collection'
                else:
                    AV=actor
                av_list=[AV,jjtitle,0,0,0,jjid,actor,album_img_link,rate,series,tags,actors,release]
                #print(len(df))
                df.loc[len(df)]=av_list  
                #print(len(df))
            #print(len(df))
            #df.loc[len(df)]=av_list   
            #print(len(df))
           
            #print (items)
            #print(av_list)
            

'''
def my_json(mag_link):
    global aria2
    
    avid_i=str(random.random())

    dl_path=Path("/volume1/aria2/_dl/",avid_i)
    if not os.path.exists(dl_path):
        os.makedirs(dl_path)

    ks=aria2.get_global_options()

    #old_dir=ks.dir
    ks.dir=str(dl_path)
    try:
        download = aria2.add_magnet(mag_link,options=ks)
    except:
        print('magnet link is failed')
    ks.dir="/volume1/aria2/_dl"


'''

javdb_legend='javdb_legend.json'   # for legend album, new seed updated, for fjl5 only...
if os.path.isfile(javdb_legend):
    df_acc=pd.read_json(javdb_legend)
else:
    df_acc=pd.DataFrame([],columns=['mlink','date','actor','id','release'])
list_acc=set(df_acc['mlink'].tolist())


check_fn='my collection.json'  # already downloaded list
if os.path.isfile(check_fn):    
    df_check=pd.read_json(check_fn)
    check_list=list(set(df_check['ID']))
else:
    check_list=[]
    
#print("check_list",check_list)



javdb_fn="my javdb.json"    # my database table , for directory check
df=pd.read_json(javdb_fn)

id_list=list(set(df['ID']))
cid_list=list(set(df.loc[df['AV'].str.contains('Collection',na=False),'ID'].tolist()))
   
argc=len(sys.argv)  
print("USAGE:")
print(" -p start_page end_page")
print(" -il initial_link for page search")
print(" -q ssis")
print(" -nl or -all") #not legend, default is legend
print(" -am") #== -fdo , all magnets, default is new magnets only
print(" -nm -u") #if the magnet link match keyword '-u'            no mozack
print(" -cc ") #if the magnet link match keyword '-C'            no mozack
print(" -fda") #force download again, default is skip downloaded albums , check my collection,
print(" -fdm") #force download again, default is skip downloaded albums , check mag file
print(" -fdo") #force download old seed, no matter how old
print(" -m") #manually check for each album, download or not?
print(" -actors_file") # read actors from file
print(" -nc") # no collection (skip collection album)
print(" -unc") # uncensor
print(" ================================")

pages=[[1,1]]
forces=[]
nms=[]
i=1
j=1
i_link='https://javdb.com/censored'
query=''
if argc==1:
    i=1
    j=1
    i_link='https://javdb.com/censored'
#else:
argv_=re.findall(r"'([^']+)'",str(sys.argv))
pages=re.findall(r"((?<='-p',\s')\d+)',\s'(\d+)'",str(sys.argv))
not_legends=re.findall(r"(-nl|-all)",str(sys.argv))  #default is finding legends
#print(not_legends)
all_magnets=re.findall(r"(-am)",str(sys.argv))
forces=re.findall(r"(-fda)",str(sys.argv))
forces_m=re.findall(r"(-fdm)",str(sys.argv))
forces_o=re.findall(r"(-fdo)",str(sys.argv))
actors_file=re.findall(r"(-actors_file)",str(sys.argv))
manuals=re.findall(r"(-m)",str(sys.argv))
ncs=re.findall(r"(-nc)",str(sys.argv))
uncs=re.findall(r"(-unc)",str(sys.argv))
querys=re.findall(r"((?<='-q',\s')\w+)",str(sys.argv))
print(querys)
links=re.findall(r"((?<='-il',\s')[^']+)",str(sys.argv))
nms=re.findall(r"(-nm)",str(sys.argv))
ccs=re.findall(r"(-cc)",str(sys.argv))
ucs=re.findall(r"(-uc)",str(sys.argv))
#print('nms=',nms)
print(sys.argv)
print(pages)
    
#print(len(nms),len(not_legends))

    
if len(pages)==1:
    i=int(pages[0][0])
    j=int(pages[0][1])
if len(links)==1:
    i_link=links[0]
if len(querys)==1:
    query='&q='+querys[0]+'&f=download'
    i_link='https://javdb.com/search'    
if len(uncs)>0:
    i_link='https://javdb.com/uncensored'
print(i,j,i_link)
#print(len(nms),len(not_legends))
#quit()
#print(len(nms),len(not_legends))    
    
mag_links=[]

#df=pd.DataFrame([[],[],[],[]])
#df.columns=['mlink','actor','id','json']
#print(df_acc)
t_now=pd.Timestamp.now()
t_1year=t_now-pd.Timedelta(365,'d')
t_10year=t_now-pd.Timedelta(3650,'d')
t_h1year=t_now-pd.Timedelta(270,'d')
t_1month=t_now-pd.Timedelta(30,'d')
t_1week=t_now-pd.Timedelta(7,'d')
#quit()

final_link=[]


#print(len(nms))
    
if len(actors_file)==1:
    with open(Path('w:/actors_name.txt'),'r') as fp:  # multiple root link from file
        txt=fp.read()
        ll=txt.split('\n')
        for f in ll:
            kkkmj.get_actor_pwd(f) #trial run 
           
else:
    ll=[i_link]  #only one root link from command line

fdone=[]    
#print(len(nms))

#driver=webdriver.Chrome()
#driver.set_window_size(1120, 550)

for f in ll:  # for each root link , 
    #print('loop',len(nms))
    if 'http' in f:
        i_link=f
    else:
        fl=kkkmj.get_actor_link(f)
        print(fl)
        i_link=fl

    if len(pages)==0:
        i=1
        #driver = webdriver.PhantomJS()

        #sleep(randint(10,100))
        #driver.get(i_link)        
        #source=driver.page_source

        default_context = cdp_browser.contexts[0]
        page = default_context.pages[0]

        # Navigate to a URL
        #my_delay()
        page.goto(i_link)

        # Perform actions or extract data using Playwright's API
        source=page.content()



        #r=requests.get(i_link)
        #source=r.text
        av_nick_names=re.findall(r"section-meta\">([^<]+)",source,flags=re.DOTALL)
        if len(av_nick_names)>0:
            album_no=av_nick_names[-1].split(' ')
            j=int(int(album_no[0])/40)+1


    while True: #  for each page 
        print('page,',i)
        if i>j: # for each page
            
            break   
        
       
        
        
        #https://javdb.com/search?q=cjod-396&f=all
        #https://javdb.com/censored

        #s_link='https://javdb.com/search?q='+m_link+'&f=all'
        s_link=i_link+'?page='+str(i)+query
        print(s_link)
        i=i+1

        #driver = webdriver.PhantomJS()
        #driver=webdriver.Chrome()
        #driver.set_window_size(1120, 550)
        #sleep(randint(10,100))
        #driver.get(s_link)
        #source=driver.page_source


        default_context = cdp_browser.contexts[0]
        page = default_context.pages[0]

        # Navigate to a URL
        #my_delay()
        page.goto(s_link)      

        # Perform actions or extract data using Playwright's API
        source=page.content()

       

        #r=requests.get(s_link)
        #source=r.text


        links=re.findall(r"<a\s{1}href=\"([^\"]+(?=\"\sclass=\"box\")).+?((?<=<strong>)[^<]+)</stron.+?<div\sclass=\"meta\">\n\s+([^\n]+).+?((?<=<div\sclass=\"tags\shas-addons\">).+?(?=</div>))",source,flags=re.DOTALL)
        #print(links)  
        #quit()
        #print(len(nms))

        
        
        for al,aid,release_dates,dl_link in links:  # for each album of the page
            #release_dates=adate.strip()
            #print(len(nms))
            print('checking...',aid)
            #if aid.upper()=='IPX-015':
            #    input('pause')
            if len(forces)==0:
                if aid.upper() in check_list:
                    print (aid,"已下載完成,可播放")
                    continue  # continue, restart the loop 
            
            if len(ncs)>0:
                if aid.upper() in cid_list:
                    #if df.loc[df['ID'].str.contains(aid.upper())]['AV'].to_list()[0]=='Collection':
                    print('skip collection album',aid)
                    continue

                
                    
            if len(not_legends)==0:  # =;
                if pd.Timestamp(release_dates)>t_h1year:   #release in half a year, is not legend album.
                    print('not legend album, skip... ',al,release_dates)
                    continue
            

            
            if len(manuals)>0:
                print(aid, al, release_dates)
                x=input("download it or not? ")
                print(x)
                if x in ['0','1','y','Y','a','A']:
                    print('true')
                    pass
                else:
                    print('false')
                    continue
            
            if not ('tag is-warning' in dl_link or 'tag is-success' in dl_link):  #not '含磁錬'
                continue
        
            m_link='https://javdb.com'+al   # +'?locale=zh'
            final_link=final_link+[m_link]
            print(m_link)
            

            #sleep(randint(10,100))
            #driver.get(m_link)
            #source=driver.page_source
            default_context = cdp_browser.contexts[0]
            page = default_context.pages[0]

            # Navigate to a URL
            #my_delay()
            page.goto(m_link)

            # Perform actions or extract data using Playwright's API
            source=page.content()    

          
            #r=requests.get(m_link)
            #source=r.text
            #old
            #items=re.findall(r"<strong>([^<]+)</strong>\s+<strong\sclass=\"current-title\">([^<]+)<",source)
            #actors=re.findall(r"<a\s{1}href=\"/actors/[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">",source)
            
            #new
            items=re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"current-title\">([^<]+)<",source)
            item2s=re.findall(r"video-detail[\w\W]+?<strong>([^<]+)</strong>[\w\W]+?class=\"origin-title\">([^<]+)<",source)
            if len(item2s)>0: # to remove the chinese translation version
                items=item2s
            actors=re.findall(r"<a\s{1}href=\"/actors/([^\"]+)[^>]+>([^<]+)</a><strong\sclass=\"symbol\sfemale\">",source)         
            series=re.findall(r"<a\shref=\"/series[^>]+>([^<]+)",source)
            tags=re.findall(r"<a\shref=\"/tags[^>]+>([^<]+)",source)
            rates=re.findall(r"((?<=&nbsp;)[0-9\.]+(?=分))",source)
            releases=re.findall(r"日期:[\w\W]+?class=\"value\">([^<]+)</span>",source)
            album_img_links=re.findall(r"class=\"video-meta-panel\"[\w\W]+?<img\ssrc=\"([^\"]+)\"\sclass=\"video-cover\"",source)
            if len(album_img_links)>0:
                album_img_link=album_img_links[0]
            else:
                album_img_link=''
            if len(rates)>0:
                rate=rates[0]
            else:
                rate='0.0'
            if len(releases)>0:
                release=releases[0]
            else:
                release=''

            
            

            
            add_myjavdb(items,album_img_link,rate,series,tags,actors,release) #將album資料存到myjavdb 
            
            print(actors)

            #fn_actor=actor_links[0][1]
            mag_links_new=re.findall(r"<a\shref=\"(magnet:[^\"]+(?=\"\stitle=)).+?((?<=class=\"time\">)[^<]+)",source,flags=re.DOTALL) 
            #print(len(mag_links_new),len(nms))
            #quit()
            t_mag_links=mag_links_new.copy()  #準備將不必要的刪除
            for mag_link in t_mag_links: 
                print(mag_link)
                magd=pd.Timestamp(mag_link[1])
                if len(all_magnets)==0 and len(forces_o)==0: #COMMAND LINE中強制DOWNLOAD ALL LINKS
                    if magd<t_h1year:
                        print('seed too old',mag_link[1])
                        mag_links_new.remove(mag_link)
                        continue #removed, skip this maglink
                        
                if len(nms)>0 : 
                    #print('found -nm or -U in command---',nms[0].lower() in mag_link[0].lower(),'---')
                    if not ('-u' in mag_link[0].lower()):  # if '-uc' can not be found in the mag-Link     [0] is maglink, [1] is date
                        mag_links_new.remove(mag_link)
                        continue            #removed, skip this maglink
                if len(ccs)>0: 
                    #print('found -nm or -U in command---',nms[0].lower() in mag_link[0].lower(),'---')
                    if not ('-c' in mag_link[0].lower()):  # if '-uc' can not be found in the mag-Link     [0] is maglink, [1] is date
                        mag_links_new.remove(mag_link)
                        continue            #removed, skip this maglink 
                if len(ucs)>0: 
                    #print('found -nm or -U in command---',nms[0].lower() in mag_link[0].lower(),'---')
                    if not (('-u' in mag_link[0].lower()) or ('-c' in mag_link[0].lower())):  # if '-uc' can not be found in the mag-Link     [0] is maglink, [1] is date
                        mag_links_new.remove(mag_link)
                        continue            #removed, skip this maglink 

                if mag_link[0] in list_acc:
                    print('此mlink已曾經下載過',mag_link[0])
                    
                    if len(forces_m)==0: # force download again, even the maglink has been downloaded.
                        mag_links_new.remove(mag_link) #removed, no need to download
                        continue
                            
                 
            df_new=pd.DataFrame(mag_links_new,columns=['mlink','date'])
           
            if len(actors)==1:
                df_new['actor']=actors[0][1]
            else:
                if len(actors)>1:
                    df_new['actor']='Collection'
                else:
                    df_new['actor']=''
            df_new['id']=aid
            df_new['release']=release_dates
            
            mag_links=df_new['mlink'].tolist()
            print(len(mag_links))
            if len(mag_links)>0:
                input('press to continue...')
            for mag_link in mag_links:
                print('my_json=>',mag_link)
                #my_json(mag_link)

                add_txt_maglink(mag_link)
                #add_javdb_maglink(mag_link)  # add to aria2 download list

            print('finished')
            
            
            df_acc=mydfcat([df_acc,df_new])
            #print(df_acc)
            #print(df_new)
            #print(len(df_acc))
            #quit()
            #mag_links=mag_links+mag_links_new
            #print(mag_links)
            #print(len(mag_links))
            #input("pause")

#df_acc.to_excel(javdb_legend,index=False)        
#df.to_excel(javdb_fn,index=False)

#with open('final_link.txt','w') as fw:
#    txt='\n'.join(final_link)
#    fw.write(txt)
    
print(df_acc)

df_acc.reset_index(drop=True,inplace=True)  
try:
    df_acc.to_json(javdb_legend,index=False)  
except: 
    print('cannot write to javdb_legend.json, maybe file is open?')

df.reset_index(drop=True,inplace=True)    
try:  
    df.to_json(javdb_fn,index=False)
except: 
    print('cannot write to my javdb.json, maybe file is open?')

df_maglink.reset_index(drop=True,inplace=True)  
try:   
    df_maglink.to_json(maglink_fn,index=False)
except: 
    print('cannot write to maglink_added.json, maybe file is open?')
try:    
    os.remove(Path('w:/myjavdb.lock'))
except:
    print('cannot remove lock file, please remove it manually')    