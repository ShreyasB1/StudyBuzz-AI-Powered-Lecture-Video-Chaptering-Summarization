from langchain_community.llms import VLLM

llm = VLLM(
    model="openai/gpt-oss-120b",
    trust_remote_code=True,  # mandatory for hf models
    # max_new_tokens=128,
    # top_k=10,
    # top_p=0.95,
    # temperature=0.8,
    # tensor_parallel_size=8,
)

print(llm.invoke("What is the capital of France ?"))
print("TESTING", llm.invoke("what is your name?"))
