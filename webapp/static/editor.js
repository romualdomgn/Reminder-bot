function telegramHtmlToEditorHtml(tgHtml) {
  return String(tgHtml || "").replace(/\n/g, "<br>");
}

function findAncestorTag(node, root, tagNames) {
  let cur = node && node.nodeType === Node.TEXT_NODE ? node.parentNode : node;
  while (cur && cur !== root) {
    if (cur.nodeType === Node.ELEMENT_NODE && tagNames.includes(cur.tagName)) {
      return cur;
    }
    cur = cur.parentNode;
  }
  return null;
}

function unwrapElement(el) {
  const parent = el.parentNode;
  if (!parent) return;
  while (el.firstChild) {
    parent.insertBefore(el.firstChild, el);
  }
  parent.removeChild(el);
}

function toggleCustomInlineTag(editor, tagName) {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0) return;
  const range = sel.getRangeAt(0);
  if (!editor.contains(range.commonAncestorContainer)) return;

  const upper = tagName.toUpperCase();
  const existing = findAncestorTag(range.commonAncestorContainer, editor, [upper]);

  if (existing) {
    if (range.collapsed) {
      const zwsp = document.createTextNode("\u200B");
      existing.parentNode.insertBefore(zwsp, existing.nextSibling);
      const nextRange = document.createRange();
      nextRange.setStart(zwsp, 1);
      nextRange.collapse(true);
      sel.removeAllRanges();
      sel.addRange(nextRange);
    } else {
      unwrapElement(existing);
    }
    return;
  }

  const wrapper = document.createElement(tagName);
  if (range.collapsed) {
    const zwsp = document.createTextNode("\u200B");
    wrapper.appendChild(zwsp);
    range.insertNode(wrapper);
    const nextRange = document.createRange();
    nextRange.setStart(zwsp, 1);
    nextRange.collapse(true);
    sel.removeAllRanges();
    sel.addRange(nextRange);
    return;
  }

  const frag = range.extractContents();
  if (tagName === "code") {
    wrapper.textContent = frag.textContent || "";
  } else {
    frag.querySelectorAll(tagName).forEach((nested) => unwrapElement(nested));
    wrapper.appendChild(frag);
  }
  range.insertNode(wrapper);

  const nextRange = document.createRange();
  nextRange.selectNodeContents(wrapper);
  sel.removeAllRanges();
  sel.addRange(nextRange);
}

function clearSelectionFormatting(editor) {
  const sel = window.getSelection();
  if (!sel || sel.rangeCount === 0 || !editor.contains(sel.getRangeAt(0).commonAncestorContainer)) {
    const plain = (editor.innerText || "").replace(/\u200B/g, "");
    editor.innerHTML = telegramHtmlToEditorHtml(escapeHtml(plain));
    return;
  }
  const range = sel.getRangeAt(0);
  if (range.collapsed) {
    const plain = (editor.innerText || "").replace(/\u200B/g, "");
    editor.innerHTML = telegramHtmlToEditorHtml(escapeHtml(plain));
    return;
  }
  const plainText = range.toString().replace(/\u200B/g, "");
  const ancestor = findAncestorTag(range.commonAncestorContainer, editor, [
    "B", "STRONG", "I", "EM", "U", "INS", "S", "STRIKE", "DEL", "CODE", "TG-SPOILER",
  ]);
  if (ancestor && ancestor.textContent === range.toString()) {
    unwrapElement(ancestor);
  } else {
    range.deleteContents();
    const tn = document.createTextNode(plainText);
    range.insertNode(tn);
    const nextRange = document.createRange();
    nextRange.selectNodeContents(tn);
    sel.removeAllRanges();
    sel.addRange(nextRange);
  }
}

function serializeEditorNode(node) {
  if (node.nodeType === Node.TEXT_NODE) {
    return escapeHtml((node.nodeValue || "").replace(/\u200B/g, ""));
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const tag = node.tagName.toUpperCase();
  if (tag === "BR") return "\n";

  const children = Array.from(node.childNodes);
  let inner = "";
  for (let idx = 0; idx < children.length; idx++) {
    const child = children[idx];
    if (
      child.nodeType === Node.ELEMENT_NODE &&
      (child.tagName === "DIV" || child.tagName === "P")
    ) {
      const onlyBr =
        child.childNodes.length === 1 &&
        child.firstChild.nodeType === Node.ELEMENT_NODE &&
        child.firstChild.tagName === "BR";
      const blockContent = onlyBr ? "" : serializeEditorNode(child);
      if (inner.length > 0 && !inner.endsWith("\n")) inner += "\n";
      inner += blockContent;
      if (idx < children.length - 1) inner += "\n";
    } else {
      inner += serializeEditorNode(child);
    }
  }

  if (tag === "B" || tag === "STRONG") return inner ? `<b>${inner}</b>` : "";
  if (tag === "I" || tag === "EM") return inner ? `<i>${inner}</i>` : "";
  if (tag === "U" || tag === "INS") return inner ? `<u>${inner}</u>` : "";
  if (tag === "S" || tag === "STRIKE" || tag === "DEL") return inner ? `<s>${inner}</s>` : "";
  if (tag === "CODE" || tag === "PRE" || tag === "TT") {
    const plainCode = escapeHtml((node.textContent || "").replace(/\u200B/g, ""));
    return plainCode ? `<code>${plainCode}</code>` : "";
  }
  if (tag === "TG-SPOILER") return inner ? `<tg-spoiler>${inner}</tg-spoiler>` : "";

  if (tag === "SPAN" && inner) {
    const style = node.style || {};
    let wrapped = inner;
    const dec = `${style.textDecoration || ""} ${style.textDecorationLine || ""}`;
    if (style.fontWeight === "bold" || Number(style.fontWeight) >= 600) wrapped = `<b>${wrapped}</b>`;
    if (style.fontStyle === "italic") wrapped = `<i>${wrapped}</i>`;
    if (dec.includes("underline")) wrapped = `<u>${wrapped}</u>`;
    if (dec.includes("line-through")) wrapped = `<s>${wrapped}</s>`;
    return wrapped;
  }

  return inner;
}

function serializeEditorToTelegramHtml(editor) {
  let out = serializeEditorNode(editor).replace(/\u200B/g, "");
  out = out.replace(/\n+$/g, "").replace(/^\n+/g, "");
  return out.trim();
}

function initRichTextEditor(editorId, toolbarId, initialTgHtml) {
  const editor = document.getElementById(editorId);
  const toolbar = document.getElementById(toolbarId);
  if (!editor || !toolbar) return null;

  editor.innerHTML = telegramHtmlToEditorHtml(initialTgHtml);

  let savedRange = null;
  let lastTouchTime = 0;

  function saveSelection() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editor.contains(sel.getRangeAt(0).commonAncestorContainer)) {
      savedRange = sel.getRangeAt(0).cloneRange();
    }
  }

  function ensureSelectionInEditor() {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && editor.contains(sel.getRangeAt(0).commonAncestorContainer)) {
      return;
    }
    editor.focus();
    if (!sel) return;
    if (savedRange) {
      sel.removeAllRanges();
      sel.addRange(savedRange);
    } else {
      const range = document.createRange();
      range.selectNodeContents(editor);
      range.collapse(false);
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }

  function refreshToolbarState() {
    const sel = window.getSelection();
    const anchor =
      sel && sel.rangeCount > 0 && editor.contains(sel.getRangeAt(0).commonAncestorContainer)
        ? sel.getRangeAt(0).commonAncestorContainer
        : null;

    let cmdBold = false;
    let cmdItalic = false;
    let cmdUnderline = false;
    let cmdStrike = false;
    if (anchor) {
      try {
        cmdBold = document.queryCommandState("bold");
        cmdItalic = document.queryCommandState("italic");
        cmdUnderline = document.queryCommandState("underline");
        cmdStrike = document.queryCommandState("strikeThrough");
      } catch (_) {}
    }

    const states = {
      bold: Boolean(anchor && (cmdBold || findAncestorTag(anchor, editor, ["B", "STRONG"]))),
      italic: Boolean(anchor && (cmdItalic || findAncestorTag(anchor, editor, ["I", "EM"]))),
      underline: Boolean(anchor && (cmdUnderline || findAncestorTag(anchor, editor, ["U", "INS"]))),
      strikeThrough: Boolean(anchor && (cmdStrike || findAncestorTag(anchor, editor, ["S", "STRIKE", "DEL"]))),
      code: Boolean(anchor && findAncestorTag(anchor, editor, ["CODE"])),
      spoiler: Boolean(anchor && findAncestorTag(anchor, editor, ["TG-SPOILER"])),
    };

    toolbar.querySelectorAll("[data-fmt]").forEach((btn) => {
      const cmd = btn.dataset.fmt;
      btn.classList.toggle("active-blue", Boolean(states[cmd]));
    });
  }

  function applyFormat(cmd) {
    ensureSelectionInEditor();
    if (cmd === "code") {
      toggleCustomInlineTag(editor, "code");
    } else if (cmd === "spoiler") {
      toggleCustomInlineTag(editor, "tg-spoiler");
    } else if (cmd === "clear") {
      clearSelectionFormatting(editor);
    } else {
      document.execCommand(cmd, false, null);
    }
    saveSelection();
    refreshToolbarState();
  }

  editor.addEventListener("paste", (e) => {
    e.preventDefault();
    const text = (e.clipboardData || window.clipboardData).getData("text/plain");
    if (document.queryCommandSupported("insertText")) {
      document.execCommand("insertText", false, text);
    } else {
      const sel = window.getSelection();
      if (sel && sel.rangeCount > 0) {
        const range = sel.getRangeAt(0);
        range.deleteContents();
        range.insertNode(document.createTextNode(text));
      }
    }
  });

  ["keyup", "mouseup", "touchend", "input"].forEach((ev) => {
    editor.addEventListener(ev, () => {
      saveSelection();
      refreshToolbarState();
    });
  });

  const onSelectionChange = () => {
    if (!document.body.contains(editor)) {
      document.removeEventListener("selectionchange", onSelectionChange);
      return;
    }
    saveSelection();
    refreshToolbarState();
  };
  document.addEventListener("selectionchange", onSelectionChange);

  toolbar.querySelectorAll("[data-fmt]").forEach((btn) => {
    let touchMoved = false;

    btn.addEventListener("touchstart", (e) => {
      e.preventDefault();
      touchMoved = false;
    }, { passive: false });

    btn.addEventListener("touchmove", () => {
      touchMoved = true;
    }, { passive: true });

    btn.addEventListener("touchend", (e) => {
      e.preventDefault();
      lastTouchTime = Date.now();
      if (!touchMoved) {
        applyFormat(btn.dataset.fmt);
      }
    }, { passive: false });

    btn.addEventListener("mousedown", (e) => {
      if (Date.now() - lastTouchTime < 500) return;
      e.preventDefault();
    });

    btn.addEventListener("click", (e) => {
      if (Date.now() - lastTouchTime < 500) return;
      e.preventDefault();
      applyFormat(btn.dataset.fmt);
    });
  });

  return {
    getHtml: () => serializeEditorToTelegramHtml(editor),
    getPlainText: () => (editor.innerText || "").replace(/\u200B/g, "").trim(),
  };
}
