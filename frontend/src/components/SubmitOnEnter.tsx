/** 让弹窗表单支持回车提交。
 *
 * antd Modal 的「确定」按钮位于 footer、在 `<Form>` 之外，表单里没有任何
 * submit 触发点，于是在输入框里按回车**什么也不会发生**——实测新建订单、
 * 修改密码等弹窗都是如此。管理员批量建订单、建用户时每次都得抬手点鼠标，
 * 是每天都在发生的摩擦（登录页能回车提交，因为那里的按钮就在 Form 内）。
 *
 * 放一个视觉隐藏的原生 submit 按钮，回车即触发表单提交 → antd 校验 → onFinish。
 * 多行文本域里的回车是换行、不触发表单提交，Select 展开时回车由其自行拦截，
 * 二者都不受影响。
 */
export default function SubmitOnEnter() {
  return <button type="submit" aria-hidden tabIndex={-1} style={{ display: 'none' }} />
}
