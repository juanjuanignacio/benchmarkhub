/* ===================================================
   LLM Benchmark Platform - Main JavaScript
   =================================================== */

'use strict';

// -------------------------------------------------------
// Theme-aware chart palette (colors validated for both
// surfaces with the six-checks palette validator).
//   categorical: fixed-order series identity (never cycle)
//   good/warn/bad: reserved status colors (score thresholds)
// -------------------------------------------------------
function bmChartPalette() {
    const dark = (document.documentElement.getAttribute('data-bs-theme') || 'dark') === 'dark';
    return dark ? {
        dark: true,
        accent: '#4C8DFF', accentFill: 'rgba(76,141,255,0.12)',
        categorical: ['#4C8DFF', '#C77E27', '#2BAA8F', '#9578E8',
                      '#D06A78', '#2E93BF', '#7FA23B', '#C56BC9'],
        good: '#28A96C', warn: '#BD7E23', bad: '#E5655E',
        tick: '#8d99ad', grid: 'rgba(148,163,184,0.10)',
    } : {
        dark: false,
        accent: '#2F6FE4', accentFill: 'rgba(47,111,228,0.10)',
        categorical: ['#2F6FE4', '#B26310', '#0F8A78', '#7C5CD6',
                      '#B84A59', '#1D7FA8', '#5F7E1E', '#A2409F'],
        good: '#178553', warn: '#9A6A00', bad: '#C13A3A',
        tick: '#5b6779', grid: 'rgba(23,32,46,0.08)',
    };
}

// -------------------------------------------------------
// Utility functions
// -------------------------------------------------------

/**
 * Get the CSRF token from cookies.
 */
function getCsrfToken() {
    const cookies = document.cookie.split(';');
    for (let cookie of cookies) {
        const [name, value] = cookie.trim().split('=');
        if (name === 'csrftoken') return decodeURIComponent(value);
    }
    return '';
}

/**
 * Show a Bootstrap toast notification.
 */
function showToast(title, message, type = 'info') {
    const toastEl = document.getElementById('testResultToast');
    if (!toastEl) return;

    const iconEl = document.getElementById('toastIcon');
    const titleEl = document.getElementById('toastTitle');
    const bodyEl = document.getElementById('toastBody');

    if (iconEl) {
        const icons = {
            success: 'bi bi-check-circle-fill text-success',
            danger: 'bi bi-x-circle-fill text-danger',
            warning: 'bi bi-exclamation-triangle-fill text-warning',
            info: 'bi bi-info-circle-fill text-info',
        };
        iconEl.className = icons[type] || icons.info;
    }
    if (titleEl) titleEl.textContent = title;
    if (bodyEl) bodyEl.textContent = message;

    const toast = bootstrap.Toast.getOrCreateInstance(toastEl);
    toast.show();
}

// -------------------------------------------------------
// Provider connection test
// -------------------------------------------------------

/**
 * Test a provider connection via AJAX.
 * Called from provider list and detail pages.
 */
function testConnection(providerId, testUrl) {
    const btn = document.querySelector(`.test-connection-btn[data-provider-id="${providerId}"]`);
    const originalHtml = btn ? btn.innerHTML : '';

    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span>';
    }

    const url = testUrl || `/providers/${providerId}/test/`;

    fetch(url, {
        method: 'POST',
        headers: {
            'X-CSRFToken': getCsrfToken(),
            'Content-Type': 'application/json',
        }
    })
    .then(r => r.json())
    .then(data => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }

        if (data.success) {
            showToast('Connection Test', `Success! Response time: ${(data.response_time || 0).toFixed(2)}s`, 'success');
        } else {
            showToast('Connection Test', `Failed: ${data.error || 'Unknown error'}`, 'danger');
        }
    })
    .catch(e => {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
        }
        showToast('Connection Test', `Error: ${e.message}`, 'danger');
    });
}

// -------------------------------------------------------
// Provider model listing
// -------------------------------------------------------

/**
 * Fetch models for a provider and populate a select element.
 */
function fetchModels(providerId, targetSelectId) {
    const url = `/providers/${providerId}/models/`;
    const select = document.getElementById(targetSelectId || 'modelSelect');

    return fetch(url)
        .then(r => r.json())
        .then(data => {
            if (data.models && data.models.length > 0 && select) {
                const current = select.value;
                select.innerHTML = '';
                data.models.forEach(model => {
                    const opt = document.createElement('option');
                    opt.value = model;
                    opt.textContent = model;
                    if (model === current) opt.selected = true;
                    select.appendChild(opt);
                });
            }
            return data.models || [];
        });
}

// -------------------------------------------------------
// Run status polling
// -------------------------------------------------------

let _runPoller = null;

/**
 * Start polling for a run's status.
 * Updates DOM elements with id: statusBadge, scoreDisplay,
 * correctDisplay, totalDisplay, answeredDisplay, progressBar, progressText
 */
function startRunPolling(runId, intervalMs) {
    intervalMs = intervalMs || 2000;
    const url = `/runs/${runId}/status/`;

    function poll() {
        fetch(url)
            .then(r => r.json())
            .then(data => {
                // Update status badge
                const badge = document.getElementById('statusBadge');
                if (badge) {
                    const label = data.status.charAt(0).toUpperCase() + data.status.slice(1);
                    badge.textContent = label;
                    badge.className = `badge status-${data.status} fs-6`;
                }

                // Update score
                const scoreEl = document.getElementById('scoreDisplay');
                if (scoreEl) {
                    scoreEl.textContent = data.score.toFixed(1) + '%';
                    // Update color class
                    scoreEl.className = scoreEl.className.replace(/text-\w+/g, '');
                    if (data.score >= 70) scoreEl.classList.add('text-success');
                    else if (data.score >= 50) scoreEl.classList.add('text-warning');
                    else scoreEl.classList.add('text-danger');
                }

                // Update counters
                const correctEl = document.getElementById('correctDisplay');
                if (correctEl) correctEl.textContent = data.correct_answers;

                const totalEl = document.getElementById('totalDisplay');
                if (totalEl) totalEl.textContent = data.total_questions;

                const answeredEl = document.getElementById('answeredDisplay');
                if (answeredEl) answeredEl.textContent = data.answered_count;

                // Update progress bar
                const pct = data.progress_pct || 0;
                const pb = document.getElementById('progressBar');
                if (pb) pb.style.width = pct + '%';

                const pt = document.getElementById('progressText');
                if (pt) pt.textContent = pct + '%';

                // If done, reload page
                if (['completed', 'failed', 'cancelled'].includes(data.status)) {
                    stopRunPolling();
                    setTimeout(() => window.location.reload(), 1500);
                }
            })
            .catch(err => console.warn('Run poll error:', err));
    }

    _runPoller = setInterval(poll, intervalMs);
    return _runPoller;
}

function stopRunPolling() {
    if (_runPoller) {
        clearInterval(_runPoller);
        _runPoller = null;
    }
}

// -------------------------------------------------------
// Confirm dialogs
// -------------------------------------------------------

/**
 * Attach confirm dialogs to all forms with data-confirm attribute.
 */
function attachConfirmDialogs() {
    document.querySelectorAll('form[data-confirm]').forEach(form => {
        form.addEventListener('submit', function(e) {
            const msg = this.dataset.confirm || 'Are you sure?';
            if (!confirm(msg)) {
                e.preventDefault();
            }
        });
    });
}

// -------------------------------------------------------
// Test connection buttons on provider list
// -------------------------------------------------------

function attachTestConnectionButtons() {
    document.querySelectorAll('.test-connection-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const id = this.dataset.providerId;
            const url = this.dataset.testUrl;
            testConnection(id, url);
        });
    });
}

// -------------------------------------------------------
// Auto-dismiss alerts
// -------------------------------------------------------

function autoDismissAlerts(delay) {
    delay = delay || 5000;
    setTimeout(() => {
        document.querySelectorAll('.alert-dismissible').forEach(alert => {
            if (bootstrap && bootstrap.Alert) {
                const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
                bsAlert.close();
            }
        });
    }, delay);
}

// -------------------------------------------------------
// Initialize on DOM ready
// -------------------------------------------------------

document.addEventListener('DOMContentLoaded', function() {
    attachConfirmDialogs();
    attachTestConnectionButtons();
    autoDismissAlerts(6000);
});
