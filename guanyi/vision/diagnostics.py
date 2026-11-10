"""Actionable model failures without exposing credentials or HTTP bodies."""


def model_error(llm, max_tokens):
    code = (llm.error or {}).get("code", "model_error")
    details = {"finish_reason": llm.finish_reason, "attempts": llm.attempts,
               "output_tokens": llm.usage.get("completion_tokens", 0),
               "reasoning_tokens": (llm.usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0),
               "max_tokens": max_tokens}
    if llm.finish_reason == "length":
        code = "output_limit"
        message = "输出预算耗尽，未获得完整识别答案（输出%d token，其中推理%d，预算%d）。" % (
            details["output_tokens"], details["reasoning_tokens"], max_tokens)
        action = "已采用关闭深度思考的提取模式；若仍发生，请减少参考图或调整输出预算，无需反复检查密钥。"
    else:
        messages = {
            "missing_api_key": ("没有配置有效的模型密钥，尚未发送请求。", "检查项目.env中的DEEPSEEK_API_KEY。"),
            "http_401": ("服务拒绝鉴权（HTTP 401）。", "核对密钥是否有效，以及密钥与服务地址是否对应。"),
            "http_402": ("服务拒绝请求（HTTP 402，通常与余额有关）。", "检查模型账户余额。"),
            "http_429": ("服务限流（HTTP 429）。", "稍等后再试，避免连续点击。"),
            "http_400": ("服务认为请求参数不受支持（HTTP 400）。", "检查服务是否支持图像、多图输入及thinking参数。"),
            "http_422": ("服务未通过请求参数校验（HTTP 422）。", "检查所选模型和兼容接口的参数支持情况。"),
            "network_error": ("无法连接模型服务。", "检查网络、代理及DEEPSEEK_BASE_URL。"),
            "timeout": ("模型请求超时。", "可稍后重试；远端可能仍在处理且可能产生用量。"),
            "empty_response": ("服务返回成功，但答案正文为空。", "查看运行记录中的finish_reason、输出用量和推理用量，判断是否仅返回推理。"),
        }
        message, action = messages.get(code, ("模型服务调用失败（%s）。" % code, "查看错误类型和运行记录；若为HTTP 5xx，可稍后重试。"))
    return {"code": code, "message": message, "action": action, "details": details}
