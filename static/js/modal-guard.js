/* ============================================================
   弹框防误关守卫

   问题：用户点「删除」，弹框经常没反应、要点好几次。

   根因（实测确认）：DaisyUI 的 dialog.modal 末尾有一段
     <form method="dialog" class="modal-backdrop"><button>close</button></form>
   这个 backdrop 铺满整个视口。弹框一打开，**触发按钮原来的位置就被 backdrop
   盖住了**，于是第二次点击落在遮罩上，把刚打开的弹框又关掉。

   实测 /clusters/9/ 删除按钮：关闭态该点命中 BUTTON（按钮本身），
   打开态命中 FORM.modal-backdrop；间隔 60/120/250/400ms 点第二下，
   以及真实 dblclick，全部立刻变回 open=false。
   于是「开→关」交替，用户看到的就是"点了没反应"，再点一下又开。

   修法：弹框刚打开的一小段时间内，忽略落在 backdrop 上的点击。
   这段时间正好覆盖住手快连点 / 误双击，之后点遮罩关闭照常可用。

   为什么放在这里而不是改 21 个 dialog：backdrop 是 DaisyUI 的标准结构，
   全项目 7 个模板共 21 处都一样，逐个改既啰嗦又会漏。这里在
   HTMLDialogElement.prototype.showModal 上打一个补丁即可全覆盖。
   ============================================================ */
(function () {
  'use strict';

  /* 守卫窗口。取 450ms：系统双击判定阈值通常 500ms 上下，
     这个值能吃掉误双击，又不会让"点遮罩关闭"明显变迟钝。 */
  var GUARD_MS = 450;

  /* 用 WeakMap 而不是 dataset：不往业务 DOM 上写属性，
     dialog 被移除后条目自动回收。 */
  var openedAt = new WeakMap();

  var proto = window.HTMLDialogElement && window.HTMLDialogElement.prototype;
  if (!proto || !proto.showModal) return; // 老浏览器没有 <dialog>，直接不管

  var nativeShowModal = proto.showModal;
  proto.showModal = function () {
    openedAt.set(this, performance.now());
    return nativeShowModal.apply(this, arguments);
  };

  /* 同一个 dialog 也可能用 show() 打开，一并盖住 */
  if (proto.show) {
    var nativeShow = proto.show;
    proto.show = function () {
      openedAt.set(this, performance.now());
      return nativeShow.apply(this, arguments);
    };
  }

  function withinGuard(dialog) {
    var t = openedAt.get(dialog);
    return typeof t === 'number' && performance.now() - t < GUARD_MS;
  }

  /* 捕获阶段拦截，必须早于 backdrop 那个 <form method="dialog"> 的默认行为。
     backdrop 内是个 <button>，点击它会提交 form 从而关闭 dialog，
     所以 click 和 submit 两条路都要堵。 */
  document.addEventListener(
    'click',
    function (e) {
      if (!e.target || !e.target.closest) return;
      var backdrop = e.target.closest('.modal-backdrop');
      if (!backdrop) return;

      var dialog = backdrop.closest('dialog');
      if (!dialog || !withinGuard(dialog)) return;

      e.preventDefault();
      e.stopPropagation();
    },
    true
  );

  document.addEventListener(
    'submit',
    function (e) {
      if (!e.target || !e.target.classList) return;
      if (!e.target.classList.contains('modal-backdrop')) return;

      var dialog = e.target.closest('dialog');
      if (!dialog || !withinGuard(dialog)) return;

      e.preventDefault();
      e.stopPropagation();
    },
    true
  );
})();
