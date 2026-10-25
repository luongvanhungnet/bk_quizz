"use strict";
(function (root) {
  function isTypingTarget(target) {
    return !!target && (["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)
      || target.isContentEditable || !!(target.closest && target.closest('[contenteditable="true"]')));
  }
  function actionForKey(event, state) {
    if (event.repeat || event.isComposing || event.ctrlKey || event.altKey || event.metaKey || event.shiftKey
      || state.busy || state.editing || state.dirty || !state.current || isTypingTarget(event.target)) return null;
    if (event.key === "ArrowLeft") return "previous";
    if (event.key === "ArrowRight") return "next";
    if (!state.reviewer || !state.sourceReady) return null;
    return { ArrowUp: "approve", ArrowDown: "reject" }[event.key] || null;
  }
  function navigationPlan(index, count, offset, total, direction, pageSize) {
    const next = index + direction;
    if (next >= 0 && next < count) return { offset, index: next };
    if (direction > 0 && offset + count < total) return { offset: offset + pageSize, index: 0 };
    if (direction < 0 && offset > 0) return { offset: Math.max(0, offset - pageSize), index: pageSize - 1 };
    return null;
  }
  const api = { isTypingTarget, actionForKey, navigationPlan };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.ReviewKeys = api;
})(typeof window === "undefined" ? {} : window);
