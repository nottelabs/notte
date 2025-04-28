# Running benchmarks

Running benchmarks should be as easy as running this command:

❯ `cat benchmarks/benchmark_params.toml | uv run python -m notte_eval.run`

We chose to use a toml file (being piped into the module) because it makes it easy to reproduce experiments, ensuring that we always keep the correct parameters. (see [example toml](/examples/benchmark_params) for relevant parameters we can tune). In this toml file we select which agent to benchmark, on which dataset and which external evaluator to use for determining if the task was handled correctly. For now we support the webvoyager benchmark with the default webvoyager evaluator, but integrating new agents and benchmarks is pretty straightforward!

# Benchmark results

Once a task runs, it creates a folder with the following structure (in current working directory):

```
webvoyager # benchmark name
└── Falco # agent name
    ├── 1741604281 # timestamp of run
    │   ├── Allrecipes_3 # id of the task
    │   │   └── 0 # run_id (useful if we try multiple times each task)
    │   │       ├── results.json # full results
    │   │       ├── results_no_screenshot.json # results, stripping away b64 screenshots for easier readability
    │   │       └── summary.webp # screenshots in animated webp
    │   └── params.json # parameters for this run
    ...
```

Each task runs independently, and will create its own subfolder.
The resulting json files will look something like this:

```
{
  "success": bool,
  "run_id": int,
  "eval": null | {"success": bool, "reason": bool},
  "duration_in_s": float,
  "agent_answer": str,
  "task": {
    "question": str,
    "id": str,
    "answer": str,
    "url": str,
    "website_name": str
  },
  "steps": [
    {
      "url":str,
      "llm_calls": [
        {
          "input_tokens": int,
          "output_tokens": int,
          "messages_in": [
            {
              "role": "system",
              "content": str
            },
            {
              "role": "user",
              "content": str
            },
          ],
          "message_out": {
            "content": str,
            "role": "assistant",
          },
          "pretty_out": str
        }
      ],
      "duration_in_s": float
    },
  ],
  "logs": {},
  "task_description": str,
  "task_id": str,
  "task_website": str,
  "reference_answer":str,
  "total_input_tokens": int,
  "total_output_tokens": int,
  "last_message": str
}


```
