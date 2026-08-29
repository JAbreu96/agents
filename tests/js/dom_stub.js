/*
 * A DOM small enough to hold job_fields.js and nothing else.
 *
 * The file under test touches four things -- document.createElement,
 * document.createTextNode, a handful of element properties, and
 * addEventListener -- so the stub implements exactly those. It is deliberately
 * not a browser: there is no layout, no CSS, no parsing. What it does model
 * faithfully is the parent chain and event propagation, because that is the
 * part job_fields.js reasons about (see `guard`/`stop` in create()).
 *
 * Anything the file starts using that is not here fails loudly as a TypeError
 * rather than silently passing, which is the behaviour we want from a stub.
 */
'use strict';

class ClassList {
  constructor(el) { this.el = el; }
  _list() { return (this.el.className || '').split(/\s+/).filter(Boolean); }
  _set(list) { this.el.className = list.join(' '); }
  add(...names) {
    const list = this._list();
    names.forEach(n => { if (!list.includes(n)) list.push(n); });
    this._set(list);
  }
  remove(...names) { this._set(this._list().filter(n => !names.includes(n))); }
  contains(name) { return this._list().includes(name); }
  toggle(name, force) {
    const on = force === undefined ? !this.contains(name) : !!force;
    if (on) this.add(name); else this.remove(name);
    return on;
  }
}

class Node {
  constructor(tagName) {
    this.tagName = (tagName || '').toUpperCase();
    this.children = [];
    this.parentNode = null;
    this.listeners = new Map();
    this.dataset = {};
    this.style = {};
    this.className = '';
    this._text = '';
    /*
     * Every element carries a string `value`, the way a real input does before
     * anyone types. A real <select> derives its value from the selected option;
     * this one does not, so a handler that reads select.value here sees
     * whatever was last assigned, or ''.
     */
    this.value = '';
    // Layout is not modelled; these exist so checkMarkdownOverflow can run.
    this.scrollHeight = 0;
    this.clientHeight = 0;
    this.classList = new ClassList(this);
  }

  appendChild(child) {
    child.parentNode = this;
    this.children.push(child);
    return child;
  }

  append(...nodes) { nodes.forEach(n => this.appendChild(n)); }

  replaceWith(node) {
    if (!this.parentNode) return;
    const kids = this.parentNode.children;
    const at = kids.indexOf(this);
    if (at < 0) return;
    node.parentNode = this.parentNode;
    kids.splice(at, 1, node);
    this.parentNode = null;
  }

  remove() {
    if (!this.parentNode) return;
    const kids = this.parentNode.children;
    const at = kids.indexOf(this);
    if (at >= 0) kids.splice(at, 1);
    this.parentNode = null;
  }

  addEventListener(type, fn) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push(fn);
  }

  get textContent() {
    if (this.children.length === 0) return this._text;
    return this.children.map(c => c.textContent).join('');
  }

  set textContent(value) {
    this.children.forEach(c => { c.parentNode = null; });
    this.children = [];
    this._text = value === null || value === undefined ? '' : String(value);
  }

  // childNodes and children are the same list here: this stub has no notion
  // of a node that is not an element, so nothing distinguishes them.
  get childNodes() { return this.children; }

  /*
   * There is no HTML parser here. Assigning markup clears the children and
   * keeps the string verbatim, so a test can see *that* markup was set but
   * never walk into it. job_fields.js assigns markup at exactly two sites --
   * a `&times;` glyph and a one-span empty state -- and inspects neither.
   */
  get innerHTML() { return this._html || (this.children.length ? '<...>' : ''); }
  set innerHTML(value) {
    this.textContent = '';
    this._html = value === '' ? '' : String(value);
  }

  focus() { this.focused = true; }

  // Depth-first, class selectors only -- the one call site asks for
  // '.markdown-field'.
  querySelectorAll(selector) {
    if (!selector.startsWith('.')) {
      throw new Error(`dom_stub: only class selectors are supported, got ${selector}`);
    }
    const want = selector.slice(1);
    const found = [];
    const walk = (node) => {
      node.children.forEach(child => {
        if (child.classList.contains(want)) found.push(child);
        walk(child);
      });
    };
    walk(this);
    return found;
  }

  // Every descendant, self included -- for tests that sweep a built subtree.
  descendants() {
    const out = [this];
    this.children.forEach(c => out.push(...c.descendants()));
    return out;
  }
}

class TextNode extends Node {
  constructor(text) {
    super('#text');
    this._text = text === null || text === undefined ? '' : String(text);
  }
}

const document = {
  createElement: (tag) => new Node(tag),
  createTextNode: (text) => new TextNode(text),
};

/*
 * Fire an event at `target` and let it bubble, honouring stopPropagation.
 * Returns the elements whose listeners actually ran, so a test can assert
 * where propagation stopped rather than merely that nothing threw.
 */
function dispatch(target, type) {
  const reached = [];
  const event = {
    type,
    target,
    stopped: false,
    defaultPrevented: false,
    stopPropagation() { this.stopped = true; },
    preventDefault() { this.defaultPrevented = true; },
  };
  let node = target;
  while (node) {
    const fns = node.listeners.get(type);
    if (fns && fns.length) {
      reached.push(node);
      for (const fn of fns) {
        fn.call(node, event);
        if (event.stopped) return { reached, event };
      }
    }
    node = node.parentNode;
  }
  return { reached, event };
}

module.exports = { Node, TextNode, document, dispatch };
