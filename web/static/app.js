// Mobile nav hamburger toggle. Pure aria-expanded toggling; CSS does the
// rest via the sibling selector. Closes on outside tap, on ESC, and on
// link tap so the dropdown doesn't linger after navigation.
(function () {
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.getElementById('site-nav');
  if (!toggle || !nav) return;
  const i18n = window.__clodexCheckI18n || {};

  function setOpen(open) {
    toggle.setAttribute('aria-expanded', open ? 'true' : 'false');
    toggle.setAttribute('aria-label', open ? (i18n.menu_close || 'Close menu') : (i18n.menu_open || 'Open menu'));
  }

  toggle.addEventListener('click', (e) => {
    e.stopPropagation();
    const isOpen = toggle.getAttribute('aria-expanded') === 'true';
    setOpen(!isOpen);
  });

  // Close on tap outside the dropdown.
  document.addEventListener('click', (e) => {
    if (toggle.getAttribute('aria-expanded') !== 'true') return;
    if (nav.contains(e.target) || toggle.contains(e.target)) return;
    setOpen(false);
  });

  // Close after a nav link is tapped — otherwise the panel stays open over
  // the new page transition (jarring on mobile).
  nav.addEventListener('click', (e) => {
    if (e.target.tagName === 'A') setOpen(false);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') setOpen(false);
  });
})();


// Custom model-name combobox: type-to-filter + tap-to-select.
// Replaces native <datalist> because iOS Safari / WeChat browser don't show
// it reliably on mobile.
(function () {
  const input = document.getElementById('model');
  const list = document.getElementById('model-list');
  if (!input || !list) return;
  let items = Array.from(list.querySelectorAll('.combo-item'));

  // De-emphasize non-matches instead of hiding them. Users repeatedly
  // expected the dropdown to show ALL probed models even after typing a
  // partial name (so they can compare options or pick a sibling). Hiding
  // made the relay's full whitelist invisible — exactly the opposite of
  // what /api/probe was meant to surface. Dimming preserves discoverability
  // while still highlighting the current text query.
  function filter(q) {
    const ql = (q || '').toLowerCase().trim();
    items.forEach((it) => {
      const v = (it.getAttribute('data-value') || '').toLowerCase();
      const match = ql === '' || v.includes(ql);
      it.classList.toggle('no-match', !match);
      it.hidden = false;
    });
    list.hidden = items.length === 0;
  }

  function bindItem(it) {
    // pointerdown beats focus loss; preventDefault keeps input focused so
    // mobile keyboard doesn't close before we set the value.
    it.addEventListener('pointerdown', (e) => {
      e.preventDefault();
      input.value = it.getAttribute('data-value');
      list.hidden = true;
      input.blur();
    });
  }
  items.forEach(bindItem);

  // Exposed so the probe layer can replace the suggestions with whatever
  // the relay actually advertises. Falls back to the static template list
  // if probe fails / relay doesn't expose /v1/models.
  window.clodexSetModelChoices = function (values) {
    list.innerHTML = '';
    values.forEach((v) => {
      const li = document.createElement('li');
      li.className = 'combo-item';
      li.setAttribute('data-value', v);
      li.textContent = v;
      list.appendChild(li);
    });
    items = Array.from(list.querySelectorAll('.combo-item'));
    items.forEach(bindItem);
  };

  input.addEventListener('focus', () => filter(input.value));
  input.addEventListener('input', () => filter(input.value));
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') list.hidden = true;
  });

  document.addEventListener('pointerdown', (e) => {
    if (e.target === input || list.contains(e.target)) return;
    list.hidden = true;
  });
})();


// Pre-submission probe: hit /api/probe on api_key blur, render an inline
// pill below the api_key input describing what the relay carries, replace
// the model dropdown with the actually-available models, and (when the
// current protocol has 0 matches) offer one-click handoff to a protocol
// the relay DOES carry.
(function () {
  const detectForm = document.getElementById('detect-form');
  function getActiveProtocol() {
    if (detectForm && detectForm.getAttribute('data-protocol')) {
      return detectForm.getAttribute('data-protocol');
    }
    return location.pathname.startsWith('/claude') ? 'anthropic' :
      location.pathname.startsWith('/openai') ? 'openai' :
      location.pathname.startsWith('/gemini') ? 'gemini' : null;
  }
  if (!getActiveProtocol()) return;

  const protoPath = {anthropic: '/claude', openai: '/openai', gemini: '/gemini'};
  const i18n = window.__clodexCheckI18n || {};

  const baseUrlInput = document.getElementById('base_url');
  const apiKeyInput = document.getElementById('api_key');
  const modelInput = document.getElementById('model');
  if (!baseUrlInput || !apiKeyInput) return;

  // Inject pill container right after the api_key field's hint.
  const apiKeyField = apiKeyInput.closest('.field');
  const pill = document.createElement('div');
  pill.id = 'probe-pill';
  pill.className = 'probe-pill';
  pill.hidden = true;
  apiKeyField.appendChild(pill);

  let inflight = null;
  let lastKey = null;

  async function runProbe() {
    const protocol = getActiveProtocol();
    if (!protocol) return;
    const baseUrl = baseUrlInput.value.trim();
    const apiKey = apiKeyInput.value.trim();
    if (!baseUrl || !apiKey || apiKey.length < 8) return;
    if (!/^https?:\/\//.test(baseUrl)) return;

    const key = protocol + '|' + baseUrl + '|' + apiKey.length + ':' + apiKey.slice(-4);
    if (key === lastKey) return; // already probed this combo
    lastKey = key;

    setPill('neutral', '🔄 ' + (i18n.detecting || 'Detecting...'));
    if (inflight) inflight.abort && inflight.abort();
    const ctrl = new AbortController();
    inflight = ctrl;

    const fd = new FormData();
    fd.set('base_url', baseUrl);
    fd.set('api_key', apiKey);
    fd.set('protocol', protocol);
    let r, data;
    try {
      r = await fetch('/api/probe', {method: 'POST', body: fd, signal: ctrl.signal});
      data = await r.json();
    } catch (e) {
      if (e.name === 'AbortError') return;
      setPill('warn', '⚪ ' + (i18n.probe_failed || 'Probe failed, but detection can continue') + ' — ' + (i18n.probe_direct_try || 'the entered model will be tried directly'));
      setSubmitEnabled(true);
      return;
    }
    if (r.status === 429) {
      setPill('warn', '⚠ ' + (data.error || (i18n.probe_rate_limited || 'Probe rate limited, try again later')) + ' (' + (i18n.probe_can_continue || 'detection can continue') + ')');
      lastKey = null;
      setSubmitEnabled(true);
      return;
    }
    renderProbeResult(data, protocol);
  }

  window.clodexRunProbe = function () {
    lastKey = null;
    runProbe();
  };

  function renderProbeResult(data, protocol) {
    const protoLabel = {anthropic: 'Claude', openai: 'OpenAI', gemini: 'Gemini'}[protocol] || protocol;
    if (!data.ok) {
      if (data.auth_ok === false) {
        setPill('fail', '🔴 ' + (data.error || (i18n.auth_failed || 'Authentication failed')));
      } else {
        setPill('warn', '⚪ ' + (data.error || (i18n.probe_failed || 'Probe failed, but detection can continue')) + ' — ' + (i18n.probe_can_continue || 'detection can continue'));
        setSubmitEnabled(true);
      }
      return;
    }

    if (!data.models_endpoint_supported) {
      setPill('neutral', '⚪ ' + (data.note || (i18n.models_unavailable || 'This relay does not expose /v1/models')) + ' (' + (i18n.probe_can_continue || 'detection can continue') + ')');
      setSubmitEnabled(true);
      return;
    }

    const myModels = (data.by_protocol && data.by_protocol[protocol]) || [];
    const total = data.raw_count || 0;

    if (myModels.length === 0) {
      const others = Object.keys(data.by_protocol || {})
        .filter((p) => p !== protocol && data.by_protocol[p].length > 0)
        .map((p) => ({proto: p, count: data.by_protocol[p].length, sample: data.by_protocol[p][0]}));

      let html =
        '<div class="probe-headline">🟡 ' + escapeHtml((i18n.models_none_for_protocol || 'This relay has no {label} models').replace('{label}', protoLabel)) + '</div>' +
        '<div class="probe-detail">' + escapeHtml((i18n.models_seen_other_protocol || 'Found {total} models, but none match this check protocol.').replace('{total}', total)) + '</div>';
      if (others.length) {
        html += '<div class="probe-actions">';
        others.forEach((o) => {
          const label = {anthropic: 'Claude', openai: 'OpenAI', gemini: 'Gemini'}[o.proto];
          html +=
            '<button type="button" class="btn btn-ghost probe-action" data-handoff="' + o.proto + '">' +
            (i18n.switch_protocol || 'Switch to {label} protocol').replace('{label}', label) +
            ' (' + escapeHtml((i18n.usable_count || '{count} usable').replace('{count}', o.count)) + ')</button>';
        });
        html += '</div>';
      }
      setPillHtml('warn', html);
      bindHandoff(protocol);
      if (others.length > 0) {
        setSubmitEnabled(false, protoLabel + ': ' + (i18n.models_unavailable || 'This relay does not expose /v1/models'));
      } else {
        setSubmitEnabled(true);
      }
      return;
    }

    const sample = myModels.slice(0, 4).join(', ');
    const more = myModels.length > 4 ? ` +${myModels.length - 4}` : '';
    setPillHtml(
      'ok',
      '<div class="probe-headline">🟢 ' + escapeHtml((i18n.models_usable_for_check || '{total} available models, {count} usable for this check').replace('{total}', total).replace('{count}', myModels.length)) + '</div>' +
      '<div class="probe-detail">' + escapeHtml(sample) + escapeHtml(more) + '</div>'
    );

    if (window.clodexSetModelChoices) {
      window.clodexSetModelChoices(myModels);
    }
    setSubmitEnabled(true);
    window.clodexBestByProtocol = data.best_by_protocol || {};

    const best = (data.best_by_protocol && data.best_by_protocol[protocol]) || myModels[0];
    if (modelInput && modelInput.value.trim() && !myModels.includes(modelInput.value.trim())) {
      modelInput.value = best;
    }
  }

  function setPill(level, text) {
    pill.className = 'probe-pill probe-' + level;
    pill.textContent = text;
    pill.hidden = false;
  }
  function setPillHtml(level, html) {
    pill.className = 'probe-pill probe-' + level;
    pill.innerHTML = html;
    pill.hidden = false;
  }

  function setSubmitEnabled(ok, reason) {
    const btn = document.getElementById('submit-btn');
    if (!btn) return;
    btn.disabled = !ok;
    btn.title = ok ? '' : (reason || '');
  }

  function bindHandoff(currentProto) {
    pill.querySelectorAll('[data-handoff]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const target = btn.getAttribute('data-handoff');
        if (detectForm && detectForm.dataset.pelicanStandalone === 'true') {
          const protoBtn = document.querySelector('.proto-switch-btn[data-pelican-proto="' + target + '"]');
          if (protoBtn) {
            protoBtn.click();
            return;
          }
        }
        try {
          sessionStorage.setItem('clodex_check:handoff', JSON.stringify({
            base_url: baseUrlInput.value.trim(),
            api_key: apiKeyInput.value.trim(),
            from: currentProto,
          }));
        } catch (_) { /* sessionStorage unavailable */ }
        location.href = protoPath[target];
      });
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  apiKeyInput.addEventListener('blur', runProbe);
  baseUrlInput.addEventListener('blur', () => {
    lastKey = null;
    runProbe();
  });
  if (modelInput) {
    modelInput.addEventListener('input', () => {
      if (modelInput.value.trim()) setSubmitEnabled(true);
    });
  }

  document.querySelectorAll('.preset-btn[data-preset-url]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const presetUrl = btn.getAttribute('data-preset-url');
      const presetModel = btn.getAttribute('data-preset-model');
      if (presetUrl) {
        baseUrlInput.value = presetUrl;
        lastKey = null;
      }
      if (presetModel && modelInput) {
        modelInput.value = presetModel;
      }
      if (apiKeyInput.value.trim().length >= 8) {
        runProbe();
      } else {
        apiKeyInput.focus();
      }
    });
  });

  try {
    const raw = sessionStorage.getItem('clodex_check:handoff');
    if (raw) {
      sessionStorage.removeItem('clodex_check:handoff');
      const data = JSON.parse(raw);
      if (data && data.base_url && data.api_key) {
        baseUrlInput.value = data.base_url;
        apiKeyInput.value = data.api_key;
        const fromLabel = {anthropic: 'Claude', openai: 'OpenAI', gemini: 'Gemini'}[data.from] || data.from;
        setPill('neutral', '🔄 ' + (i18n.notice || 'Loaded credentials from {label} page, reprobing...').replace('{label}', fromLabel));
        setTimeout(runProbe, 50);
      }
    }
  } catch (_) { /* malformed handoff */ }
})();


(function () {
  const form = document.getElementById('detect-form');
  if (!form) return;
  const submitBtn = document.getElementById('submit-btn');
  const errBox = document.getElementById('form-error');
  const i18n = window.__clodexCheckI18n || {};
  const isStandalonePelican = form.dataset.pelicanStandalone === 'true';
  let activeTab = isStandalonePelican ? 'pelican' : 'audit';

  function currentProtocol() {
    return form.getAttribute('data-protocol')
      || (location.pathname.startsWith('/claude') ? 'anthropic'
        : location.pathname.startsWith('/openai') ? 'openai'
        : location.pathname.startsWith('/gemini') ? 'gemini'
        : 'anthropic');
  }

  function endpointFor() {
    return form.getAttribute('data-endpoint')
      || (location.pathname.startsWith('/claude')
        ? '/api/detect/claude'
        : location.pathname.startsWith('/openai')
        ? '/api/detect/openai'
        : location.pathname.startsWith('/gemini')
        ? '/api/detect/gemini'
        : '/api/detect');
  }

  function setTab(tab, updateUrl) {
    if (isStandalonePelican) return;
    activeTab = tab === 'pelican' ? 'pelican' : 'audit';
    form.dataset.activeTab = activeTab;
    document.querySelectorAll('.check-tab-btn[data-check-tab]').forEach((btn) => {
      const on = btn.getAttribute('data-check-tab') === activeTab;
      btn.classList.toggle('is-active', on);
      btn.setAttribute('aria-selected', on ? 'true' : 'false');
    });
    form.querySelectorAll('[data-audit-only="true"]').forEach((el) => {
      el.hidden = activeTab === 'pelican';
    });
    form.querySelectorAll('[data-pelican-only="true"]').forEach((el) => {
      el.hidden = activeTab !== 'pelican';
    });
    if (submitBtn && !submitBtn.disabled) {
      submitBtn.textContent = activeTab === 'pelican'
        ? (i18n.draw_pelican || 'Draw Pelican (SVG)')
        : (i18n.start_detection || 'Start check');
    }
    if (updateUrl && history.replaceState) {
      const url = new URL(location.href);
      if (activeTab === 'pelican') {
        url.searchParams.set('tab', 'pelican');
      } else {
        url.searchParams.delete('tab');
      }
      history.replaceState(null, '', url.toString());
    }
  }

  const tabBtns = document.querySelectorAll('.check-tab-btn[data-check-tab]');
  if (tabBtns.length) {
    tabBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        setTab(btn.getAttribute('data-check-tab'), true);
      });
    });
    const params = new URLSearchParams(location.search);
    if (params.get('tab') === 'pelican' || location.hash === '#pelican') {
      setTab('pelican', false);
    } else {
      setTab('audit', false);
    }
  }

  // Standalone /pelican protocol switcher (Claude / OpenAI / Gemini)
  const protoSwitchBtns = document.querySelectorAll('.proto-switch-btn[data-pelican-proto]');
  if (protoSwitchBtns.length) {
    const protoHidden = document.getElementById('pelican_protocol');
    const presetBtn = document.getElementById('pelican-preset-btn');
    const baseUrlInput = document.getElementById('base_url');
    const modelInput = document.getElementById('model');

    protoSwitchBtns.forEach((btn) => {
      btn.addEventListener('click', () => {
        const proto = btn.getAttribute('data-pelican-proto');
        const defUrl = btn.getAttribute('data-default-url') || '';
        const defModel = btn.getAttribute('data-default-model') || '';

        protoSwitchBtns.forEach((b) => {
          const on = b === btn;
          b.classList.toggle('is-active', on);
          b.setAttribute('aria-selected', on ? 'true' : 'false');
        });
        form.setAttribute('data-protocol', proto);
        if (protoHidden) protoHidden.value = proto;
        if (presetBtn) {
          presetBtn.setAttribute('data-preset-url', defUrl);
          presetBtn.setAttribute('data-preset-model', defModel);
        }
        if (baseUrlInput) {
          baseUrlInput.placeholder = defUrl;
          // Auto-adjust clodex.xyz root <-> /v1 if user already filled clodex.xyz
          const cur = baseUrlInput.value.trim().replace(/\/+$/, '');
          if (cur === 'https://clodex.xyz' || cur === 'https://clodex.xyz/v1') {
            baseUrlInput.value = defUrl;
          }
        }
        if (modelInput) {
          modelInput.value = defModel;
          modelInput.placeholder = defModel;
        }
        const map = window.__pelicanModelsByProtocol || {};
        if (window.clodexSetModelChoices && Array.isArray(map[proto])) {
          window.clodexSetModelChoices(map[proto]);
        }
        if (submitBtn) submitBtn.disabled = false;
        if (window.clodexRunProbe) window.clodexRunProbe();
      });
    });
  }

  // Light / Dark canvas toggle on inline pelican result
  const inlineBgBtn = document.getElementById('pelican-inline-bg-btn');
  const inlineStage = document.getElementById('pelican-inline-stage');
  if (inlineBgBtn && inlineStage) {
    inlineBgBtn.addEventListener('click', () => {
      const isDark = inlineStage.classList.toggle('is-dark');
      inlineBgBtn.textContent = isDark
        ? (i18n.pelican_light_bg || 'Light canvas')
        : (i18n.pelican_dark_bg || 'Dark canvas');
    });
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }

  function renderPelicanInline(data) {
    const box = document.getElementById('pelican-inline-result');
    if (!box) {
      if (data.result_url) location.href = data.result_url;
      return;
    }
    const p = data.pelican || {};
    const perf = data.performance || {};
    const usage = perf.usage || {};
    const sa = perf.stream_analysis || {};

    const titleEl = document.getElementById('pelican-res-title');
    const metaEl = document.getElementById('pelican-res-meta');
    const stageEl = document.getElementById('pelican-inline-stage');
    const imgEl = document.getElementById('pelican-inline-img');
    const emptyEl = document.getElementById('pelican-inline-empty');
    const statsEl = document.getElementById('pelican-inline-stats');
    const metricsEl = document.getElementById('pelican-inline-metrics');
    const dlEl = document.getElementById('pelican-inline-svg-dl');
    const cmpEl = document.getElementById('pelican-inline-compare');
    const repEl = document.getElementById('pelican-inline-report');

    if (titleEl) {
      titleEl.textContent = (data.model || 'Model') + ' · ' + Math.round(Number(p.score || data.total_score || 0)) + '/100';
    }
    if (metaEl) {
      metaEl.textContent = (data.base_url || '') + ' · ' + (data.protocol || '');
    }
    if (repEl && data.result_url) repEl.href = data.result_url;
    if (cmpEl && data.compare_url) cmpEl.href = data.compare_url;

    if (p.valid_svg && p.svg_b64) {
      if (imgEl) imgEl.src = 'data:image/svg+xml;base64,' + p.svg_b64;
      if (stageEl) stageEl.hidden = false;
      if (emptyEl) emptyEl.hidden = true;
      if (dlEl && data.svg_url) {
        dlEl.href = data.svg_url;
        dlEl.setAttribute('download', 'clodex-pelican-' + (data.job_id || 'svg') + '.svg');
        dlEl.hidden = false;
      }
      if (inlineBgBtn) inlineBgBtn.hidden = false;
    } else {
      if (stageEl) stageEl.hidden = true;
      if (dlEl) dlEl.hidden = true;
      if (inlineBgBtn) inlineBgBtn.hidden = true;
      if (emptyEl) {
        emptyEl.hidden = false;
        const reason = data.error || p.reason || '';
        emptyEl.innerHTML = '<strong>' + escapeHtml(i18n.pelican_invalid || 'Model did not return a valid SVG') + '</strong>' +
          (reason ? '<p class="muted small">' + escapeHtml(reason) + '</p>' : '');
      }
    }

    if (statsEl) {
      const pills = [
        '<span>' + escapeHtml(i18n.pelican_score || 'Score') + ': <strong>' + Math.round(Number(p.score || 0)) + '/100</strong></span>',
        '<span>' + escapeHtml(i18n.pelican_shapes || 'Shapes') + ': <strong>' + Number(p.primitive_count || 0) + '</strong></span>',
        '<span>' + escapeHtml(i18n.pelican_colors || 'Colors') + ': <strong>' + Number(p.unique_colors || 0) + '</strong></span>',
        '<span>' + escapeHtml(i18n.pelican_size || 'SVG size') + ': <strong>' + Number(p.svg_bytes || 0).toLocaleString() + ' B</strong></span>',
      ];
      if (p.view_box) {
        pills.push('<span>viewBox: <code>' + escapeHtml(p.view_box) + '</code></span>');
      }
      statsEl.innerHTML = pills.map((h) => '<span class="hub-pill">' + h + '</span>').join('');
    }

    if (metricsEl) {
      const ttftText = perf.ttft_ms != null ? Number(perf.ttft_ms).toLocaleString() + 'ms' : '—';
      const latText = perf.total_latency_ms != null ? Number(perf.total_latency_ms).toLocaleString() + 'ms' : '—';
      let tpsVal = perf.tokens_per_second;
      if (!tpsVal && usage.output_tokens && perf.total_latency_ms) {
        tpsVal = (usage.output_tokens * 1000.0) / perf.total_latency_ms;
      }
      const tpsText = tpsVal ? Number(tpsVal).toFixed(1) : '—';
      let streamSub = '';
      if (sa.verdict === 'real_stream') {
        streamSub = '<div class="metric-sub is-ok">' + escapeHtml(i18n.stream_real || 'True stream') + ' · ' + Number(sa.chunk_count || 0) + ' ch</div>';
      } else if (sa.verdict === 'buffered_burst') {
        streamSub = '<div class="metric-sub is-warn">' + escapeHtml(i18n.stream_buffered || '⚠ Buffered burst') + '</div>';
      } else if (sa.verdict === 'short_stream') {
        streamSub = '<div class="metric-sub">' + escapeHtml(i18n.stream_short || 'Short stream') + '</div>';
      }
      const outTok = usage.output_tokens ? Number(usage.output_tokens).toLocaleString() : '—';
      metricsEl.innerHTML =
        '<div class="metric"><div class="metric-label">' + escapeHtml(i18n.metric_ttft || 'First token') + '</div><div class="metric-value">' + ttftText + '</div></div>' +
        '<div class="metric' + (sa.verdict === 'buffered_burst' ? ' metric-warn' : '') + '"><div class="metric-label">' + escapeHtml(i18n.metric_tps || 'Throughput (T/s)') + '</div><div class="metric-value">' + tpsText + '</div>' + streamSub + '</div>' +
        '<div class="metric"><div class="metric-label">' + escapeHtml(i18n.metric_latency || 'Total latency') + '</div><div class="metric-value">' + latText + '</div></div>' +
        '<div class="metric"><div class="metric-label">' + escapeHtml(i18n.metric_output || 'Output tokens') + '</div><div class="metric-value">' + outTok + '</div></div>';
    }

    box.hidden = false;
    box.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  function renderModelDeadError(detail) {
    const proto = currentProtocol();
    const recommended = (window.clodexBestByProtocol || {})[proto];
    const dead = detail.model || 'model';
    const reason = detail.upstream_error || (i18n.upstream_rejected || 'upstream rejected the request');

    errBox.innerHTML = '';
    errBox.hidden = false;
    errBox.classList.add('form-error-rich');

    const title = document.createElement('div');
    title.className = 'form-error-title';
    title.textContent = i18n.model_dead_title || 'This model is not available on the relay';
    errBox.appendChild(title);

    const body = document.createElement('div');
    body.className = 'form-error-body';
    body.textContent = `${dead}: ${reason}`;
    errBox.appendChild(body);

    const actions = document.createElement('div');
    actions.className = 'form-error-actions';

    if (recommended && recommended !== dead) {
      const swapBtn = document.createElement('button');
      swapBtn.type = 'button';
      swapBtn.className = 'btn btn-primary';
      swapBtn.textContent = (i18n.swap_retry || 'Switch to {model} and retry').replace('{model}', recommended);
      swapBtn.addEventListener('click', () => {
        const modelInput = document.getElementById('model');
        if (modelInput) modelInput.value = recommended;
        errBox.hidden = true;
        errBox.classList.remove('form-error-rich');
        const force = form.querySelector('input[name="force"]');
        if (force) force.value = '';
        form.requestSubmit();
      });
      actions.appendChild(swapBtn);
    }

    const forceBtn = document.createElement('button');
    forceBtn.type = 'button';
    forceBtn.className = 'btn btn-ghost';
    forceBtn.textContent = i18n.force_submit || 'I understand, force submit';
    forceBtn.title = i18n.force_submit_title || 'Preflight can occasionally be wrong. If the model is truly dead, forced detection will produce an error report.';
    forceBtn.addEventListener('click', () => {
      let force = form.querySelector('input[name="force"]');
      if (!force) {
        force = document.createElement('input');
        force.type = 'hidden';
        force.name = 'force';
        form.appendChild(force);
      }
      force.value = '1';
      errBox.hidden = true;
      errBox.classList.remove('form-error-rich');
      form.requestSubmit();
    });
    actions.appendChild(forceBtn);

    errBox.appendChild(actions);
  }

  form.addEventListener('submit', async (ev) => {
    ev.preventDefault();
    errBox.hidden = true;
    errBox.classList.remove('form-error-rich');

    if (isStandalonePelican || activeTab === 'pelican') {
      submitBtn.disabled = true;
      const startedAt = Date.now();
      const baseLabel = i18n.drawing_pelican || 'Drawing pelican…';
      submitBtn.textContent = baseLabel + ' 0.0s';
      const timer = setInterval(() => {
        const sec = ((Date.now() - startedAt) / 1000).toFixed(1);
        submitBtn.textContent = baseLabel + ' ' + sec + 's';
      }, 200);

      const fd = new FormData();
      fd.set('protocol', currentProtocol());
      fd.set('base_url', (document.getElementById('base_url') || {}).value || '');
      fd.set('api_key', (document.getElementById('api_key') || {}).value || '');
      fd.set('model', (document.getElementById('model') || {}).value || '');
      const effortEl = document.getElementById('pelican_reasoning_effort');
      if (effortEl && effortEl.value) {
        fd.set('reasoning_effort', effortEl.value);
      }
      try {
        const startResp = await fetch('/api/pelican/start', {method: 'POST', body: fd});
        const startJson = await startResp.json().catch(() => ({detail: 'request failed'}));
        if (!startResp.ok) {
          const msg = typeof startJson.detail === 'string' ? startJson.detail : ('HTTP ' + startResp.status);
          throw new Error(msg);
        }
        const statusUrl = startJson.status_url || ('/api/pelican/status/' + startJson.job_id);
        let pollErrors = 0;
        let finalPayload = null;
        const deadline = Date.now() + 260000;
        while (Date.now() < deadline) {
          await new Promise((resolve) => setTimeout(resolve, 1200));
          let sr, sj;
          try {
            sr = await fetch(statusUrl, {cache: 'no-store'});
            sj = await sr.json().catch(() => null);
          } catch (_) {
            pollErrors += 1;
            if (pollErrors >= 5) throw new Error('Connection lost while waiting for Pelican SVG');
            continue;
          }
          if (!sr.ok || !sj) {
            pollErrors += 1;
            if (pollErrors >= 5) throw new Error('HTTP ' + (sr ? sr.status : 'error'));
            continue;
          }
          pollErrors = 0;
          if (sj.status === 'done') {
            finalPayload = sj;
            break;
          }
          if (sj.status === 'error') {
            throw new Error(sj.error || 'Pelican generation failed');
          }
        }
        if (!finalPayload) {
          throw new Error('Pelican generation timed out after 4 minutes');
        }
        renderPelicanInline(finalPayload);
      } catch (e) {
        errBox.hidden = false;
        errBox.textContent = e.message || (i18n.submit_failed || 'Submission failed');
      } finally {
        clearInterval(timer);
        submitBtn.disabled = false;
        submitBtn.textContent = i18n.draw_pelican || 'Draw Pelican (SVG)';
      }
      return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = i18n.detecting || 'Detecting...';

    const fd = new FormData(form);
    try {
      const r = await fetch(endpointFor(), {method: 'POST', body: fd});
      if (r.status === 422) {
        const j = await r.json().catch(() => ({}));
        const detail = j && j.detail;
        if (detail && detail.code === 'model_not_alive') {
          renderModelDeadError(detail);
          submitBtn.disabled = false;
          submitBtn.textContent = i18n.start_detection || 'Start check';
          return;
        }
      }
      if (!r.ok) {
        const j = await r.json().catch(() => ({detail: 'request failed'}));
        const msg = typeof j.detail === 'string' ? j.detail
          : (j.detail && j.detail.message) || ('HTTP ' + r.status);
        throw new Error(msg);
      }
      const j = await r.json();
      form.api_key.value = '';
      const force = form.querySelector('input[name="force"]');
      if (force) force.value = '';
      location.href = '/r/' + j.job_id;
    } catch (e) {
      errBox.hidden = false;
      errBox.textContent = e.message || (i18n.submit_failed || 'Submission failed');
      submitBtn.disabled = false;
      submitBtn.textContent = i18n.start_detection || 'Start check';
    }
  });
})();

// FAQ dual-mode toggle (通俗 / 开发者).
// Two <p data-mode="layperson|developer"> per question are both in DOM
// (so search engines index both); CSS hides whichever doesn't match the
// section's data-mode. Choice persists in localStorage so the user
// doesn't have to re-toggle every visit.
(() => {
  const STORAGE_KEY = 'clodex_check_faq_mode';
  const sections = document.querySelectorAll('.faq[data-mode]');
  if (!sections.length) return;

  // Restore saved preference (if any) before any clicks.
  const saved = (() => {
    try { return localStorage.getItem(STORAGE_KEY); } catch { return null; }
  })();
  if (saved === 'layperson' || saved === 'developer') {
    sections.forEach((sec) => {
      sec.dataset.mode = saved;
      sec.querySelectorAll('.faq-mode-btn').forEach((b) => {
        const active = b.dataset.mode === saved;
        b.classList.toggle('faq-mode-active', active);
        b.setAttribute('aria-selected', active ? 'true' : 'false');
      });
    });
  }

  // Click handler: switch mode + persist.
  sections.forEach((sec) => {
    sec.querySelectorAll('.faq-mode-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        const mode = btn.dataset.mode;
        if (!mode) return;
        sec.dataset.mode = mode;
        sec.querySelectorAll('.faq-mode-btn').forEach((b) => {
          const active = b === btn;
          b.classList.toggle('faq-mode-active', active);
          b.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        try { localStorage.setItem(STORAGE_KEY, mode); } catch { /* ignore */ }
      });
    });
  });
})();
