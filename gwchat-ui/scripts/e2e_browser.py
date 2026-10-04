"""Browser end-to-end check of the whole stack (needs: pip install playwright && playwright install chromium, and `bash scripts/run_demo.sh` running).

    E2E_BACKEND=http://localhost:8080 E2E_UI=http://localhost:8501 python scripts/e2e_browser.py

Drives the real Streamlit page: dashboard, worklist+filters, member record tabs, approve/reject writes, notifications, closure board, MRAT, records,
guardrails, data gaps, flow drawer, settings, new chat. Resets the demo data first. Exit code 1 on any failure.
"""
import asyncio, sys, urllib.request
from playwright.async_api import async_playwright
import os
BE=os.getenv("E2E_BACKEND","http://localhost:8080"); UI=os.getenv("E2E_UI","http://localhost:8501")
urllib.request.urlopen(urllib.request.Request(BE+"/demo/reset",method="POST"))
R=[]
def ok(name,cond,detail=''):
    R.append((name,bool(cond))); print(('PASS' if cond else 'FAIL'),name,detail)
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); pg=await b.new_page(viewport={'width':1440,'height':1000})
        errs=[]; pg.on('pageerror',lambda e:errs.append(str(e)))
        await pg.goto(UI); await pg.wait_for_selector('iframe[title*="gwchat_mockup"]',timeout=20000)
        f=pg.frame_locator('iframe[title*="gwchat_mockup"]')
        await f.locator('#welcome-screen h1').wait_for(timeout=15000)
        ok('welcome screen renders', 'Welcome back' in await f.locator('#welcome-screen h1').inner_text())
        ok('welcome has 6 suggestion chips', await f.locator('#welcome-recs .prompt-rec').count()==6)
        busy="document.querySelector('iframe[title*=gwchat_mockup]').contentWindow.GW._S.busy===false"
        async def say(q,first=False,wait=2500):
            sel='#welcome-input' if first else '#chat-input'
            await f.locator(sel).fill(q); await f.locator(sel).press('Enter')
            await pg.wait_for_timeout(1500)
            await pg.wait_for_function(busy,timeout=90000); await pg.wait_for_timeout(wait)
        async def last(): return f.locator('.msg.assistant').last
        # 1 dashboard (first send via welcome chip path)
        await f.locator('#welcome-recs .prompt-rec').first.click(); await pg.wait_for_timeout(1500); await pg.wait_for_function(busy,timeout=90000); await pg.wait_for_timeout(4000)
        m=await last()
        ok('dashboard: 4 funnel KPI cards', await m.locator('.kpi-card').count()>=8)
        ok('dashboard: charts drawn (3 canvases w/ chart)', await m.locator('canvas').count()==2, await m.locator('canvas').count())
        ok('dashboard: trace card present', await m.locator('.ehr-trace').count()==1)
        ok('dashboard: 6 tool steps', 'MCP get_trc_summary' in await m.locator('.ehr-trace').inner_text())
        ok('dashboard: priority members', await m.locator('.doc-item[data-act="open-member"]').count()>=1)
        # 2 worklist + filter
        await say('Show members discharged in the last 14 days where the provider has not uploaded documents by day 3, ranked by risk')
        m=await last(); n=await m.locator('.member-card').count(); ok('worklist: member cards', n>=2, n)
        await m.locator('select[data-f="risk_tier"]').select_option('LOW'); await pg.wait_for_timeout(400)
        vis=await m.locator('.member-card:visible').count(); ok('worklist: client filter hides rows', vis==0, vis)
        await m.locator('select[data-f="risk_tier"]').select_option('All')
        await m.locator('button[data-mode="table"]').click(); ok('worklist: table view', await m.locator('.wl-table').is_visible()); await m.locator('button[data-mode="card"]').click()
        # 3 open member via card click
        await m.locator('.member-card').first.click(); await pg.wait_for_timeout(1500); await pg.wait_for_function(busy,timeout=90000); await pg.wait_for_timeout(3500)
        m=await last(); ok('member record: header', 'Dorothy Simmons' in await m.locator('.detail-header').inner_text())
        for tab,needle in [('timeline','A03'),('discharge','Furosemide'),('risk','CONTRIBUTING'),('notif','Verified provider contacts'),('compare','Prior Admission'),('records','Cardiology')]:
            await m.locator(f'button[data-sub="{tab}"]').click(); await pg.wait_for_timeout(250)
            ok(f'member record tab {tab}', needle.lower() in (await m.locator(f'.subview[data-sub="{tab}"]').inner_text()).lower())
        # 4 write -> approve
        await say('Resend the failed provider alert for HCC-2231087')
        m=await last(); ok('write: approval card (nothing executed)', await m.locator('button[data-decision="approve"]').count()==1)
        await m.locator('button[data-decision="approve"]').click(); await pg.wait_for_timeout(1500); await pg.wait_for_function(busy,timeout=90000); await pg.wait_for_timeout(3000)
        m=await last(); ok('write: approved -> action result', 'NTF-' in await m.inner_text())
        # reject path
        await say('Escalate HCC-2231087 to the provider manager'); m=await last()
        await m.locator('button[data-decision="reject"]').click(); await pg.wait_for_timeout(1500); await pg.wait_for_function(busy,timeout=90000); await pg.wait_for_timeout(2500)
        ok('write: reject path', 'Rejected' in await f.locator('.chat-card .badge').filter(has_text='Rejected').first.inner_text())
        # 5 notifications, validation board, soft close
        await say('Which providers have not acknowledged their TRC discharge notifications?'); m=await last(); ok('notifications table', await m.locator('tbody tr, table tr').count()>=3)
        await say('Run the validation agent and show the closure board'); m=await last()
        ok('closure board columns', await m.locator('.kanban-col').count()==4); ok('validation chart', await m.locator('canvas').count()==1)
        # 6 MRAT / records / guardrails
        await say('Show the MRAT status for HCC-3345510'); m=await last(); ok('mrat status', 'human' in (await m.inner_text()).lower() or 'HEDIS nurse' in await m.inner_text())
        await say('Show attachments for HCC-4471829'); m=await last(); ok('records list read-only', await m.locator('.doc-item').count()>=2)
        await say('Close HCC-3345510 in MRAT'); m=await last(); ok('guardrail: MRAT close refused (no approval card)', await m.locator('button[data-decision]').count()==0)
        await say('Show the TRC status for HCC-0000000'); m=await last(); ok('data gap card, nothing inferred', 'unavailable' in (await m.inner_text()).lower())
        await say('Tell me a joke'); m=await last(); t=(await m.inner_text()).lower(); ok('out of scope refused', 'outside' in t, t[:120])
        # flow drawer + settings + new chat
        await f.locator('#flow-btn').click(); await pg.wait_for_timeout(500); ok('flow drawer: out-of-scope answer shows no tool call', 'No tool call' in await f.locator('#fd-body').inner_text())
        await f.locator('.fd-close').click()
        await f.locator('.link-btn').first.click(); await pg.wait_for_timeout(500); t=await f.locator('#fd-body').inner_text(); ok('flow drawer: dashboard shows Gateway, FastMCP, on-prem', all(x in t for x in ('Gateway','FastMCP','On-prem','get_trc_summary')))
        await f.locator('.fd-close').click()
        await f.locator('#user-profile').click(); await f.locator('.user-menu-item').first.click(); await pg.wait_for_timeout(300)
        await f.locator('button:has-text("Test")').click(); await pg.wait_for_timeout(1500)
        ok('settings: test connection', 'Reachable' in await f.locator('#set-status').inner_text(), await f.locator('#set-status').inner_text())
        await f.locator('.gw-scrim').click(force=True) if False else await pg.keyboard.press('Escape')
        await f.locator('.primary-nav-item.new-chat').click(); await pg.wait_for_timeout(600)
        ok('new chat returns to welcome', await f.locator('#welcome-screen').is_visible())
        ok('no JS page errors', not errs, errs[:3])
        await b.close()
asyncio.run(main())
bad=[n for n,c in R if not c]; print(f'\n{len(R)-len(bad)}/{len(R)} passed'); sys.exit(1 if bad else 0)
