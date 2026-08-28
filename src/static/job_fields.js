/*
 * Shared job-field builders for the table view (jobs.html) and the kanban
 * modal (kanban.html).
 *
 * Both views edit the same job rows through the same endpoint, so they had
 * grown two copies of every builder -- `makeDateField` / `buildModalDateField`,
 * `makeDetailField` / `buildModalTextField`, and so on -- which drifted apart
 * field by field. Notably `makeInterviewsField` was only ever written for the
 * table, so interview rounds could not be edited from the board at all.
 *
 * The two copies differed on exactly four axes, all of them presentational,
 * which is what makes one parameterised set possible:
 *
 *   fieldClass  The table wraps fields in `.detail-field` inside an expanded
 *               row; the modal wraps them in `.modal-field`.
 *   stopClicks  A click inside the table's detail row bubbles up to the row
 *               handler and collapses it, so every interactive element there
 *               stops propagation. The modal has no such ancestor handler.
 *   tagFields   The modal marks editable elements with `data-field` so it can
 *               find them again when it rebuilds; the table re-renders instead.
 *   afterSave   Saving a date refreshes the table's goal badge, but re-renders
 *               the whole board on kanban (a date can move a card).
 *
 * Everything else -- the markdown renderer, the follow-up chips, the ISO date
 * validation, `saveField` itself -- was byte-identical between the two files
 * and is shared outright.
 */
const JobFields = (function () {
  'use strict';

  // --- Pure helpers: byte-identical in both templates before extraction -----

  function rowKey(job) {
    return `${job.company}::${job.date_added}::${job.position_title || ''}::${job.link || ''}`;
  }

  function localISODate(d) {
    const yr = d.getFullYear();
    const mo = String(d.getMonth() + 1).padStart(2, '0');
    const da = String(d.getDate()).padStart(2, '0');
    return `${yr}-${mo}-${da}`;
  }

  function startOfWeekISO(d) {
    const copy = new Date(d);
    copy.setDate(copy.getDate() - copy.getDay());
    return localISODate(copy);
  }

  function isValidISODate(str) {
    if (!str) return false;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(str)) return false;
    return !isNaN(Date.parse(str));
  }

  function parseFollowupLog(raw) {
    return (raw || '').split(',').map(s => s.trim()).filter(Boolean);
  }

  function serializeFollowupLog(tokens) {
    return tokens.join(', ');
  }

  function renderMarkdownInto(container, raw) {
    container.innerHTML = '';
    const lines = (raw || '').split('\n');
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (/^\s*$/.test(line)) { i++; continue; }
      const heading = /^#{1,6}\s+(.*)$/.exec(line);
      if (heading) {
        const h = document.createElement('h4');
        appendInlineMarkdown(h, heading[1]);
        container.appendChild(h);
        i++;
        continue;
      }
      if (/^[-*]\s+/.test(line)) {
        const ul = document.createElement('ul');
        while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
          const li = document.createElement('li');
          appendInlineMarkdown(li, lines[i].replace(/^[-*]\s+/, ''));
          ul.appendChild(li);
          i++;
        }
        container.appendChild(ul);
        continue;
      }
      const para = document.createElement('p');
      let first = true;
      while (i < lines.length && !/^\s*$/.test(lines[i]) && !/^[-*]\s+/.test(lines[i]) && !/^#{1,6}\s+/.test(lines[i])) {
        if (!first) para.appendChild(document.createElement('br'));
        appendInlineMarkdown(para, lines[i]);
        first = false;
        i++;
      }
      container.appendChild(para);
    }
    if (!container.childNodes.length) {
      const empty = document.createElement('p');
      empty.className = 'markdown-empty';
      empty.textContent = '(empty)';
      container.appendChild(empty);
    }
  }

  function appendInlineMarkdown(parent, text) {
    const tokenRe = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
    let lastIndex = 0;
    let m;
    while ((m = tokenRe.exec(text)) !== null) {
      if (m.index > lastIndex) parent.appendChild(document.createTextNode(text.slice(lastIndex, m.index)));
      const token = m[0];
      if (token.startsWith('**')) {
        const strong = document.createElement('strong');
        strong.textContent = token.slice(2, -2);
        parent.appendChild(strong);
      } else if (token.startsWith('`')) {
        const code = document.createElement('code');
        code.textContent = token.slice(1, -1);
        parent.appendChild(code);
      } else {
        const linkMatch = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(token);
        if (linkMatch && /^https?:\/\//i.test(linkMatch[2])) {
          const a = document.createElement('a');
          a.href = linkMatch[2];
          a.target = '_blank';
          a.rel = 'noopener noreferrer';
          a.textContent = linkMatch[1];
          parent.appendChild(a);
        } else {
          parent.appendChild(document.createTextNode(token));
        }
      }
      lastIndex = tokenRe.lastIndex;
    }
    if (lastIndex < text.length) parent.appendChild(document.createTextNode(text.slice(lastIndex)));
  }

  function checkMarkdownOverflow(rendered, expandBtn) {
    if (rendered.classList.contains('expanded')) { return; }
    const overflowing = rendered.scrollHeight > rendered.clientHeight + 1;
    expandBtn.style.display = overflowing ? 'inline-block' : 'none';
  }

  function refreshMarkdownFields(scope) {
    scope.querySelectorAll('.markdown-field').forEach(el => {
      if (typeof el._checkOverflow === 'function') el._checkOverflow();
    });
  }

  // --- Persistence ---------------------------------------------------------

  /*
   * Writes one field of one job. The job is addressed by its full composite
   * key (company, date_added, position_title, link) because `jobs` has no
   * surrogate id.
   *
   * Mutates `job` in place on success so the caller's copy stays current
   * without a refetch, and picks up `date_applied` when the server back-fills
   * it as a side effect of moving a job to Applied.
   */
  async function saveField(job, field, value, cell) {
    const res = await fetch('/api/jobs/update', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company: job.company,
        date_added: job.date_added,
        position_title: job.position_title,
        link: job.link,
        field,
        value,
      }),
    });
    let data = {};
    try { data = await res.json(); } catch (e) { /* no body */ }
    if (res.ok) {
      job[field] = value;
      if (data.date_applied !== undefined) job.date_applied = data.date_applied;
      cell.classList.remove('saved-flash');
      void cell.offsetWidth;
      cell.classList.add('saved-flash');
    } else {
      alert(data.error || 'Failed to save change.');
      if (cell && cell.isContentEditable) {
        cell.textContent = job[field] || '';
      }
    }
    return res.ok;
  }

  /*
   * Deletes a job after confirming. The caller supplies `onDeleted` because
   * the two views clean up differently: the table just re-renders, the modal
   * has to close itself first.
   */
  async function deleteJob(job, onDeleted) {
    if (!confirm(`Delete the tracked job for ${job.company}${job.position_title ? ' — ' + job.position_title : ''}? This cannot be undone.`)) {
      return false;
    }
    const res = await fetch('/api/jobs/delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        company: job.company,
        date_added: job.date_added,
        position_title: job.position_title,
        link: job.link,
      }),
    });
    if (res.ok) {
      if (typeof onDeleted === 'function') onDeleted(job);
      return true;
    }
    let data = {};
    try { data = await res.json(); } catch (e) { /* no body */ }
    alert(data.error || 'Failed to delete job.');
    return false;
  }

  // --- Builder factory -----------------------------------------------------

  /*
   * Returns the field builders bound to one view's conventions.
   *
   * ctx:
   *   fieldClass  wrapper class for every field ('detail-field' | 'modal-field')
   *   notesClass  extra class for the roomy text fields ('' on kanban)
   *   stopClicks  attach click-stopPropagation to interactive elements
   *   tagFields   set data-field on editable elements
   *   afterSave   called after a date or follow-up write lands
   *   onDeleted   called after a successful job delete
   */
  function create(ctx) {
    const cfg = Object.assign({
      fieldClass: 'detail-field',
      notesClass: '',
      stopClicks: false,
      tagFields: false,
      afterSave: () => {},
      onDeleted: () => {},
    }, ctx || {});

    // The table's detail row collapses on any click that reaches it, so its
    // fields swallow clicks. The modal has no such ancestor and does not.
    function guard(el) {
      if (cfg.stopClicks) el.addEventListener('click', (e) => e.stopPropagation());
      return el;
    }

    function tag(el, field) {
      if (cfg.tagFields) el.dataset.field = field;
      return el;
    }

    function wrapper(extra) {
      const wrap = document.createElement('div');
      wrap.className = cfg.fieldClass + (extra || '');
      return wrap;
    }

    function labelled(wrap, label) {
      const labelEl = document.createElement('label');
      labelEl.textContent = label;
      wrap.appendChild(labelEl);
      return wrap;
    }

    // --- Date ------------------------------------------------------------

    function makeDateField(label, job, field) {
      const wrap = labelled(wrapper(), label);
      wrap.appendChild(renderDateInput(job, field));
      return wrap;
    }

    /*
     * `outreach_date` and `date_applied` predate any validation, so some rows
     * hold free text like "emailed Tuesday". Those are shown verbatim with an
     * explicit opt-in to replace them, rather than silently blanked by a date
     * input that cannot represent them.
     */
    function renderDateInput(job, field) {
      const value = job[field] || '';

      if (value && !isValidISODate(value)) {
        const box = document.createElement('div');
        box.className = 'non-date-value';
        const text = document.createElement('span');
        text.className = 'raw-text';
        text.textContent = value;
        box.appendChild(text);

        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = 'Replace with date';
        btn.addEventListener('click', (e) => {
          if (cfg.stopClicks) e.stopPropagation();
          const input = document.createElement('input');
          input.type = 'date';
          input.dataset.field = field;
          guard(input);
          input.addEventListener('change', () => {
            saveField(job, field, input.value, input).then(() => cfg.afterSave());
          });
          box.replaceWith(input);
        });
        box.appendChild(btn);
        return box;
      }

      const input = document.createElement('input');
      input.type = 'date';
      input.value = value;
      input.dataset.field = field;
      guard(input);
      input.addEventListener('change', () => {
        saveField(job, field, input.value, input).then(() => cfg.afterSave());
      });
      return input;
    }

    // --- Follow-up log ----------------------------------------------------

    function makeFollowupField(label, job, field) {
      const wrap = labelled(wrapper(), label);
      wrap.appendChild(renderFollowupField(job, field));
      return wrap;
    }

    function renderFollowupField(job, field) {
      const tokens = parseFollowupLog(job[field]);

      const box = document.createElement('div');
      box.className = 'followup-field';

      for (const token of tokens) {
        const chip = document.createElement('span');
        chip.className = 'followup-chip' + (isValidISODate(token) ? '' : ' non-date');
        const text = document.createElement('span');
        text.textContent = token;
        chip.appendChild(text);

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.innerHTML = '&times;';
        removeBtn.addEventListener('click', (e) => {
          if (cfg.stopClicks) e.stopPropagation();
          const updated = tokens.filter(t => t !== token);
          saveField(job, field, serializeFollowupLog(updated), chip).then(() => {
            box.replaceWith(renderFollowupField(job, field));
          });
        });
        chip.appendChild(removeBtn);
        box.appendChild(chip);
      }

      const addWrap = document.createElement('span');
      addWrap.className = 'followup-add';
      const dateInput = document.createElement('input');
      dateInput.type = 'date';
      guard(dateInput);
      addWrap.appendChild(dateInput);

      const addBtn = document.createElement('button');
      addBtn.type = 'button';
      addBtn.textContent = 'Add';
      // Two follow-ups is the cap; a third reads as pestering.
      addBtn.disabled = tokens.length >= 2;
      addBtn.addEventListener('click', (e) => {
        if (cfg.stopClicks) e.stopPropagation();
        if (!dateInput.value || tokens.includes(dateInput.value)) return;
        const updated = [...tokens, dateInput.value];
        saveField(job, field, serializeFollowupLog(updated), addWrap).then(() => {
          box.replaceWith(renderFollowupField(job, field));
        });
      });
      addWrap.appendChild(addBtn);
      box.appendChild(addWrap);

      return box;
    }

    // --- Plain text -------------------------------------------------------

    function makeDetailField(label, job, field, isNotes) {
      const wrap = labelled(wrapper(isNotes ? cfg.notesClass : ''), label);

      const editable = document.createElement('div');
      editable.className = 'editable';
      editable.contentEditable = 'true';
      editable.textContent = job[field] || '';
      tag(editable, field);
      guard(editable);
      editable.addEventListener('blur', () => {
        const value = editable.textContent.trim();
        if (value !== (job[field] || '')) {
          saveField(job, field, value, editable);
        }
      });
      wrap.appendChild(editable);

      return wrap;
    }

    // --- Markdown ---------------------------------------------------------

    function makeMarkdownField(label, job, field) {
      const wrap = wrapper(cfg.notesClass + ' markdown-field');

      const headerRow = document.createElement('div');
      headerRow.className = 'markdown-field-header';
      const labelEl = document.createElement('label');
      labelEl.textContent = label;
      headerRow.appendChild(labelEl);
      const editBtn = document.createElement('button');
      editBtn.type = 'button';
      editBtn.className = 'linklike';
      editBtn.textContent = 'Edit';
      headerRow.appendChild(editBtn);
      wrap.appendChild(headerRow);

      const rendered = document.createElement('div');
      rendered.className = 'editable markdown-rendered';
      renderMarkdownInto(rendered, job[field]);
      tag(rendered, field);
      guard(rendered);
      wrap.appendChild(rendered);

      const expandBtn = document.createElement('button');
      expandBtn.type = 'button';
      expandBtn.className = 'linklike markdown-expand-btn';
      expandBtn.textContent = 'Show more';
      expandBtn.style.display = 'none';
      expandBtn.addEventListener('click', (e) => {
        if (cfg.stopClicks) e.stopPropagation();
        const expanded = rendered.classList.toggle('expanded');
        expandBtn.textContent = expanded ? 'Show less' : 'Show more';
      });
      wrap.appendChild(expandBtn);

      wrap._checkOverflow = () => checkMarkdownOverflow(rendered, expandBtn);

      editBtn.addEventListener('click', (e) => {
        if (cfg.stopClicks) e.stopPropagation();
        const textarea = document.createElement('textarea');
        textarea.className = 'editable markdown-raw';
        textarea.value = job[field] || '';
        tag(textarea, field);
        guard(textarea);
        textarea.addEventListener('blur', () => {
          const value = textarea.value.trim();
          const finish = () => {
            const fresh = document.createElement('div');
            fresh.className = 'editable markdown-rendered';
            renderMarkdownInto(fresh, job[field]);
            tag(fresh, field);
            guard(fresh);
            textarea.replaceWith(fresh);
            expandBtn.textContent = 'Show more';
            wrap._checkOverflow = () => checkMarkdownOverflow(fresh, expandBtn);
            wrap._checkOverflow();
          };
          if (value !== (job[field] || '')) {
            saveField(job, field, value, textarea).then(finish);
          } else {
            finish();
          }
        });
        expandBtn.style.display = 'none';
        rendered.replaceWith(textarea);
        textarea.focus();
      });

      return wrap;
    }

    // --- Delete -----------------------------------------------------------

    function makeDeleteField(job) {
      const wrap = wrapper();
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'delete-job-btn';
      btn.textContent = 'Delete Job';
      btn.addEventListener('click', (e) => {
        if (cfg.stopClicks) e.stopPropagation();
        deleteJob(job, cfg.onDeleted);
      });
      wrap.appendChild(btn);
      return wrap;
    }

    return {
      makeDateField,
      renderDateInput,
      makeFollowupField,
      renderFollowupField,
      makeDetailField,
      makeMarkdownField,
      makeDeleteField,
    };
  }

  return {
    rowKey,
    localISODate,
    startOfWeekISO,
    isValidISODate,
    parseFollowupLog,
    serializeFollowupLog,
    renderMarkdownInto,
    appendInlineMarkdown,
    checkMarkdownOverflow,
    refreshMarkdownFields,
    saveField,
    deleteJob,
    create,
  };
})();
