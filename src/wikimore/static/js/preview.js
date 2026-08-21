(function () {
    'use strict';

    var body = document.body;
    var project = body.dataset.project;
    var lang = body.dataset.lang;
    if (!project || !lang) return;

    var PREFIX = '/' + project + '/' + lang + '/wiki/';
    var SHOW_DELAY = 300;
    var HIDE_DELAY = 150;

    var tooltip = null;
    var showTimer = null;
    var hideTimer = null;
    var activeCtrl = null;

    function ensureTooltip() {
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'wm-preview';
            tooltip.setAttribute('role', 'tooltip');
            tooltip.hidden = true;
            document.body.appendChild(tooltip);
            tooltip.addEventListener('mouseenter', cancelHide);
            tooltip.addEventListener('mouseleave', scheduleHide);
        }
        return tooltip;
    }

    function cancelHide() {
        clearTimeout(hideTimer);
    }

    function scheduleHide() {
        clearTimeout(hideTimer);
        hideTimer = setTimeout(function () {
            if (tooltip) tooltip.hidden = true;
        }, HIDE_DELAY);
    }

    function esc(s) {
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function render(data, clientX, clientY) {
        var el = ensureTooltip();
        var html = '';
        var thumb = data.thumbnail;
        if (thumb && thumb.source) {
            html += '<img class="wm-preview-thumb" src="' + esc(thumb.source) + '" alt="" loading="lazy">';
        }
        html += '<div class="wm-preview-text">';
        html += '<strong class="wm-preview-title">' + esc(data.title || '') + '</strong>';
        if (data.description) {
            html += '<span class="wm-preview-desc">' + esc(data.description) + '</span>';
        }
        if (data.extract) {
            var txt = data.extract.length > 250
                ? data.extract.slice(0, 250).trimEnd() + '…'
                : data.extract;
            html += '<p class="wm-preview-extract">' + esc(txt) + '</p>';
        }
        html += '</div>';
        el.innerHTML = html;

        // measure then position
        el.hidden = false;
        var r = el.getBoundingClientRect();
        var vw = window.innerWidth;
        var vh = window.innerHeight;
        var x = clientX + 18;
        var y = clientY + 18;
        if (x + r.width > vw - 8) x = clientX - r.width - 8;
        if (y + r.height > vh - 8) y = clientY - r.height - 8;
        el.style.left = Math.max(4, x) + 'px';
        el.style.top = Math.max(4, y) + 'px';
    }

    function titleFromPathname(pathname) {
        if (!pathname || pathname.indexOf(PREFIX) !== 0) return null;
        return pathname.slice(PREFIX.length);
    }

    document.addEventListener('mouseover', function (e) {
        var a = e.target.closest('a[href]');
        if (!a) return;
        // Use a.pathname (resolved absolute path) so relative hrefs like ./Title work
        var rawTitle = titleFromPathname(a.pathname);
        if (!rawTitle) return;

        clearTimeout(showTimer);
        cancelHide();

        var cx = e.clientX;
        var cy = e.clientY;

        showTimer = setTimeout(function () {
            if (activeCtrl) activeCtrl.abort();
            var ctrl = new AbortController();
            activeCtrl = ctrl;
            fetch('/' + project + '/' + lang + '/api/preview/' + rawTitle, { signal: ctrl.signal })
                .then(function (r) { return r.ok ? r.json() : null; })
                .then(function (data) {
                    if (data && activeCtrl === ctrl) render(data, cx, cy);
                })
                .catch(function () {})
                .finally(function () {
                    if (activeCtrl === ctrl) activeCtrl = null;
                });
        }, SHOW_DELAY);
    });

    document.addEventListener('mouseout', function (e) {
        var a = e.target.closest('a[href]');
        if (!a) return;
        if (!titleFromPathname(a.pathname)) return;
        clearTimeout(showTimer);
        if (activeCtrl) { activeCtrl.abort(); activeCtrl = null; }
        scheduleHide();
    });
}());
