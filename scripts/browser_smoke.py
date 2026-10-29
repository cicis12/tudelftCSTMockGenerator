"""Exercise real desktop/mobile flows against an isolated local app (no paid API calls)."""
import os
import json
from pathlib import Path
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import zipfile

import httpx
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = ROOT / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)
with socket.socket() as sock:
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
with tempfile.TemporaryDirectory(prefix='cst-browser-') as temp:
    env = dict(os.environ, SECRET_KEY='browser-test-secret-'*3, ADMIN_PASSWORD='browser-test-password', DATABASE_URL=f'sqlite:///{temp}/app.db', OPENAI_API_KEY='', COOKIE_SECURE='false')
    process = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', str(port), '--no-access-log'], cwd=ROOT, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                if httpx.get(base+'/health').status_code == 200: break
            except httpx.TransportError: pass
            if process.poll() is not None: raise RuntimeError(process.stderr.read().decode())
            time.sleep(.1)
        else: raise RuntimeError('Preview server did not start')
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={'width':1440,'height':1100})
            errors=[]
            page.on('pageerror', lambda e: errors.append(str(e)))
            page.goto(base)
            expect(page.get_by_role('heading',name='Make this session yours')).to_be_visible()
            page.screenshot(path=str(ARTIFACTS/'home-desktop.png'),full_page=True)
            page.get_by_role('button',name='Let’s get started').click()
            expect(page.locator('#start-button')).to_be_disabled()
            page.locator('#accept-rules').check()
            page.get_by_role('button',name='Start mock').click()
            expect(page.locator('#timer')).to_be_visible()
            expect(page.get_by_role('heading',name='Formula sheet')).to_be_visible()
            assert page.locator('.katex-error').count()==0
            page.locator('.option').first.click()
            expect(page.locator('.option.selected')).to_have_count(1)
            assert page.locator('.option.correct').count()==0
            deadline_text=page.locator('#timer').text_content()
            page.reload()
            expect(page.locator('.option.selected')).to_have_count(1)
            expect(page.locator('#timer')).not_to_have_text('--:--')
            page.screenshot(path=str(ARTIFACTS/'math-desktop.png'),full_page=True)
            page.get_by_role('button',name='Finish this section').click()
            expect(page.locator('#modal-timer')).to_be_visible()
            page.get_by_role('button',name='Finish section',exact=True).click()
            expect(page.get_by_role('heading',name='Logic & reasoning',exact=True)).to_be_visible()
            assert page.get_by_role('heading',name='Formula sheet').count()==0
            page.get_by_role('button',name='End mock',exact=True).click()
            page.get_by_role('button',name='Finish & review').click()
            expect(page.get_by_role('heading',name='Good work showing up.')).to_be_visible()
            expect(page.locator('.review-question')).to_have_count(44)
            page.locator('#review-filter').select_option('incorrect')
            assert page.locator('.review-question').count()>=43
            page.screenshot(path=str(ARTIFACTS/'results-desktop.png'),full_page=True)

            mobile=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            mobile.on('pageerror', lambda e: errors.append(str(e)))
            mobile.goto(base)
            expect(mobile.get_by_role('heading',name='Make this session yours')).to_be_visible()
            assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            mobile.screenshot(path=str(ARTIFACTS/'home-mobile.png'),full_page=True)
            mobile.set_viewport_size({'width':320,'height':700})
            assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            mobile.set_viewport_size({'width':390,'height':844})
            mobile.locator('[data-action="section-choice"][data-value="math"]').click()
            mobile.locator('[data-action="mode-choice"][data-value="infinite"]').click()
            mobile.get_by_role('button',name='Let’s get started').click()
            mobile.locator('#accept-rules').check()
            mobile.get_by_role('button',name='Start practice').click()
            expect(mobile.locator('#timer')).to_have_count(0)
            mobile.get_by_role('button',name='ƒ Formula sheet').click()
            expect(mobile.locator('#modal')).to_be_visible()
            expect(mobile.locator('#modal-timer')).to_have_count(0)
            mobile.get_by_role('button',name='Close ×').click()
            mobile.locator('.option').first.click()
            mobile.get_by_role('button',name='Check answer').click()
            expect(mobile.locator('.option.correct')).to_have_count(1)
            assert mobile.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            mobile.screenshot(path=str(ARTIFACTS/'practice-mobile.png'),full_page=True)
            mobile.get_by_role('button',name='Next question').click()
            expect(mobile.get_by_role('button',name='Check answer')).to_be_disabled()
            mobile.get_by_role('button',name='Finish practice').click()
            mobile.get_by_role('button',name='Finish & review').click()
            expect(mobile.locator('.review-question')).to_have_count(2)

            page.goto(base+'/admin')
            page.get_by_label('Admin password').fill('browser-test-password')
            page.locator('#login-form button').click()
            expect(page.get_by_role('heading',name='A better question bank.')).to_be_visible()
            expect(page.locator('#gen-count')).to_have_attribute('max', '100')
            expect(page.get_by_role('button',name='Approve all',exact=True)).to_be_disabled()
            page.get_by_role('button',name='Preview the model context').click()
            expect(page.get_by_role('heading',name='What the model receives')).to_be_visible()
            page.get_by_role('button',name='Close',exact=True).click()
            page.locator('#bank-status').select_option('published')
            expect(page.get_by_role('button',name='Edit',exact=True)).to_have_count(90)
            assert page.locator('.katex-error').count()==0
            page.get_by_role('button',name='Edit',exact=True).first.click()
            page.locator('#edit-explanation').fill('A reviewed explanation that preserves the original mathematical answer.')
            page.get_by_role('button',name='Save as draft').click()
            page.locator('#bank-status').select_option('draft')
            expect(page.get_by_role('button',name='Approve & publish')).to_have_count(1)
            page.get_by_role('button',name='Approve & publish').click()
            expect(page.get_by_role('heading',name='All clear here.')).to_be_visible()
            with page.expect_download() as download_info:
                page.get_by_role('button',name='Export all questions (.zip)').click()
            download = download_info.value
            assert download.suggested_filename == 'cst-studio-questions.zip'
            archive_path = Path(temp) / download.suggested_filename
            download.save_as(archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                exported = json.loads(archive.read('questions.json'))
            assert len(exported['questions']) == 90
            imported = dict(exported['questions'][0], prompt='Imported browser question: which domain is correct?', status='draft')
            exported['questions'].append(imported)
            with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.writestr('questions.json', json.dumps(exported))
            page.locator('#import-file').set_input_files(archive_path)
            page.get_by_role('button',name='Import ZIP',exact=True).click()
            expect(page.locator('#archive-status')).to_have_text('Imported 1 question. Skipped 90 duplicates (91 questions in the archive).')
            expect(page.get_by_role('button',name='Approve & publish')).to_have_count(1)
            page.locator('#import-file').set_input_files(archive_path)
            page.get_by_role('button',name='Import ZIP',exact=True).click()
            expect(page.locator('#archive-status')).to_have_text('Imported 0 questions. Skipped 91 duplicates (91 questions in the archive).')
            page.screenshot(path=str(ARTIFACTS/'admin-desktop.png'),full_page=True)
            page.set_viewport_size({'width':390,'height':844})
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            expect(page.get_by_role('button',name='Approve all',exact=True)).to_be_enabled()
            page.screenshot(path=str(ARTIFACTS/'admin-mobile.png'),full_page=True)
            page.get_by_role('button',name='Approve all',exact=True).click()
            expect(page.get_by_role('heading',name='All clear here.')).to_be_visible()
            expect(page.get_by_role('button',name='Approve all',exact=True)).to_be_disabled()
            expect(page.locator('#admin-counts')).not_to_contain_text('draft')

            learner_page = browser.new_page(viewport={'width':1440,'height':1100})
            learner_page.on('pageerror', lambda e: errors.append(str(e)))
            learner_page.goto(base)
            learner_page.locator('[data-action="section-choice"][data-value="math"]').click()
            learner_page.locator('[data-action="mode-choice"][data-value="infinite"]').click()
            learner_page.get_by_role('button',name='Let’s get started').click()
            learner_page.locator('#accept-rules').check()
            learner_page.get_by_role('button',name='Start practice').click()
            expect(learner_page.locator('#account-button')).to_be_disabled()
            item = learner_page.evaluate('state.attempt.items[0]')
            with sqlite3.connect(f'{temp}/app.db') as db:
                snapshot = json.loads(db.execute('SELECT snapshot FROM items WHERE id = ?', (item['id'],)).fetchone()[0])
            learner_page.locator('.option').nth(snapshot['correct_index']).click()
            learner_page.get_by_role('button',name='Check answer').click()
            expect(learner_page.get_by_text('Remembered. This question will rest',exact=False)).to_be_visible()
            learner_page.get_by_role('button',name='Finish practice').click()
            learner_page.get_by_role('button',name='Finish & review').click()
            expect(learner_page.locator('[data-progress="resting"]')).to_have_text('1')
            learner_page.locator('#account-button').click()
            learner_page.get_by_role('button',name='Create account',exact=True).click()
            learner_page.locator('#learner-username').fill('browser_learner')
            learner_page.locator('#learner-password').fill('browser-learner-password')
            learner_page.locator('#learner-confirm').fill('different-password')
            learner_page.locator('#learner-submit').click()
            expect(learner_page.locator('#learner-error')).to_have_text('The passwords don’t match.')
            learner_page.locator('#learner-confirm').fill('browser-learner-password')
            learner_page.screenshot(path=str(ARTIFACTS/'account-dialog-desktop.png'))
            learner_page.locator('#learner-submit').click()
            expect(learner_page.locator('#account-button')).to_have_attribute('aria-label','Account: browser_learner')
            expect(learner_page.locator('[data-progress="resting"]')).to_have_text('1')
            learner_page.screenshot(path=str(ARTIFACTS/'progress-synced-desktop.png'),full_page=True)

            other_device = browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            other_device.on('pageerror', lambda e: errors.append(str(e)))
            other_device.goto(base)
            expect(other_device.locator('[data-progress="resting"]')).to_have_text('0')
            other_device.locator('#account-button').click()
            expect(other_device.get_by_role('button',name='Continue without an account')).to_be_visible()
            other_device.locator('#learner-username').fill('browser_learner')
            other_device.locator('#learner-password').fill('browser-learner-password')
            other_device.screenshot(path=str(ARTIFACTS/'account-dialog-mobile.png'))
            other_device.locator('#learner-submit').click()
            expect(other_device.locator('#account-button')).to_have_attribute('aria-label','Account: browser_learner')
            expect(other_device.locator('[data-progress="resting"]')).to_have_text('1')
            assert other_device.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            other_device.screenshot(path=str(ARTIFACTS/'progress-synced-mobile.png'),full_page=True)
            other_device.locator('[data-action="section-choice"][data-value="math"]').click()
            other_device.locator('[data-action="mode-choice"][data-value="infinite"]').click()
            other_device.get_by_role('button',name='Let’s get started').click()
            other_device.locator('#accept-rules').check()
            other_device.get_by_role('button',name='Start practice').click()
            expect(other_device.get_by_role('button',name='Check answer')).to_be_visible()
            assert other_device.evaluate('state.attempt.items[0].prompt') != item['prompt']
            expect(other_device.locator('#timer')).to_have_count(0)
            other_device.get_by_role('button',name='Finish practice').click()
            other_device.get_by_role('button',name='Finish & review').click()
            other_device.locator('#account-button').click()
            other_device.get_by_role('button',name='Sign out',exact=True).click()
            expect(other_device.locator('[data-progress="resting"]')).to_have_text('0')
            learner_page.reload()
            expect(learner_page.locator('[data-progress="resting"]')).to_have_text('1')
            with sqlite3.connect(f'{temp}/app.db') as db:
                qid = db.execute('SELECT question_id FROM items WHERE id = ?', (item['id'],)).fetchone()[0]
                db.execute("UPDATE questions SET status = 'draft' WHERE section = 'math' AND id != ?", (qid,))
                db.commit()
            learner_page.reload()
            expect(learner_page.get_by_role('button',name='Let’s get started')).to_be_disabled()
            expect(learner_page.get_by_text('You’re caught up.',exact=True)).to_be_visible()
            learner_page.locator('[data-action="section-choice"][data-value="logic"]').click()
            expect(learner_page.get_by_role('button',name='Let’s get started')).to_be_enabled()
            assert not errors, errors
            browser.close()
            print('Desktop + mobile browser flows passed; no JavaScript errors. Screenshots in artifacts/.')
    finally:
        process.terminate()
        process.wait(timeout=10)
