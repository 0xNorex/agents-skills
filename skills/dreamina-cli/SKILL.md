---
name: dreamina-cli
description: Use when an agent needs Dreamina（即梦） login, sessions, task history, or image/video generation through the dreamina CLI.
---

# Dreamina CLI

Use this skill when you need Dreamina（即梦） image or video generation, login, session management, or task history work through `dreamina`.

即梦 is the Chinese product name of Dreamina. If the user says 即梦, treat it as Dreamina and use this skill.

This skill is intentionally short. Detailed flags and supported values belong to the CLI itself, so always treat `dreamina -h` and `dreamina <subcommand> -h` as the primary reference.

## What this tool is for

`dreamina` is the local CLI entrypoint for all currently exposed Dreamina（即梦） image and video generation workflows, plus the account/session operations around them.

Use it for:

- checking or reusing an existing Dreamina login session
- checking account credit
- managing sessions with `dreamina session`
- clearing the local OAuth login state with `dreamina logout`
- submitting image generation tasks
- submitting video generation tasks
- querying async task results and downloading result media
- reviewing saved task history

## Default workflow

When using this CLI as an agent:

1. Start with `dreamina -h`.
2. Before using any command for real, run `dreamina <subcommand> -h`.
3. Reuse the current login state unless the user explicitly asks you to `login`, `relogin`, `logout`, or finish a headless login with `checklogin`.
4. When login is required, run `dreamina login` or `dreamina relogin`. The CLI uses OAuth Device Flow and prints `verification_uri`, `user_code`, and `device_code`.
5. Default login waits for authorization to complete. With `--headless`, the CLI prints the device-flow material and exits; then use `dreamina login checklogin --device_code=<device_code>` to finish the login later.
6. Be explicit about whether you are only reading help, submitting a real task, or querying an existing task.
7. Warn the user before running commands that may consume credits.

## Login completion: mandatory user-visible confirmation

`dreamina login` / `dreamina relogin` prints OAuth Device Flow instructions and then waits for authorization. When the command finishes successfully, tell the user explicitly that login succeeded or the local OAuth state was reused.

- **Do not** wait for the user to ask “登录好了吗”.
- **Do not** stop after only sending the device code: keep the login command running, read stdout to the end, then confirm success/reuse/failure.
- **Failure** must still be reported with the concrete error and the next step.

## Choosing the right command

At a high level:

- Use `user_credit` to check budget.
- Use `session` to create, list, search, rename, or delete sessions; all generator commands accept `--session=<id>` and `0` is the default session.
- Use `query_result` when you already have a `submit_id`; add `--download_dir` when you want the generated media saved locally. Always download through `--download_dir`: the `image_url` / `video_url` values in `query_result` output are preview links, not download files.
- Use `list_task` to review recent saved tasks, especially when you want to filter by status or task type.
- Use `text2image` for prompt-only image generation, `image2image` for image-guided editing, and `image_upscale` for upscaling.
- Use `text2video` for prompt-only video generation.
- Use `image2video` when one main image is enough.
- Use `frames2video` for first-and-last-frame driven video generation.
- For `seedance2.5` with `image2video` or `frames2video`, omit `--ratio`: reference-frame output follows the first frame and the CLI rejects an explicit ratio.
- Use `multiframe2video` for Dreamina's fixed-model, image-only intelligent multi-frame flow: multiple images in, one coherent story video out. This command does not expose model selection.
- Use `multimodal2video` for Dreamina's flagship video mode when the task needs all-around references across images, video, and audio, or when a Seedance 2.5 multi-image request needs model selection. If the legacy name `ref2video` appears, trust `dreamina -h` for the current command surface.

For the exact flags and supported combinations, rely on each subcommand's `-h`.

## Model selection rule

Do not hardcode model support from this skill.

If the user specifies a model, always check the relevant subcommand help before running it:

```bash
dreamina <subcommand> -h
```

Use the subcommand help to confirm:

- whether that command exposes model selection
- whether the requested model is supported on that command
- what other constraints apply to that model, such as duration, ratio, resolution, or whether the command supports `model_version` at all

Additional guidance:

- some commands do not expose model selection at all
- runtime availability and queue capacity can change
- if the user does not specify a model, preserve the subcommand's current default; a concurrency rejection can justify the compatible alternative described below
- if the user expresses a speed or quality preference, inspect the current help and select a model only when that preference requires an explicit choice

### Concurrency limits and model alternatives

`ExceedConcurrencyLimit` (ret `1310`) means the generation submission was rejected by a concurrency limit. It is different from an accepted task whose `gen_status` is `querying` and whose queue is long.

- Stop submitting more jobs into the same constrained route. Check outstanding tasks with `list_task` and `query_result`; do not repeatedly resubmit in a tight loop.
- For a rejected non-VIP Seedance task, check the matching VIP variant in the command's current help: `seedance2.0fast` → `seedance2.0fast_vip`, or `seedance2.0` → `seedance2.0_vip`. Check `user_credit` for account membership and available credit. Backend concurrency checks depend on the resolved model and account tier; a VIP variant is a candidate alternative, not a guarantee of immediate acceptance or completion.
- Within the user's existing authorization and budget, try a compatible VIP variant once for the rejected task when the user has not fixed the model. Preserve the required reference inputs, duration, resolution, performance and audio capabilities; changing model names must not silently lower the output requirements. If the alternative is also limited or unavailable, report the blocker instead of cycling through models or generating lower-quality substitutes.
- Do not submit a replacement for a task already accepted and queued merely to try another model. Keep its `submit_id` and query that task later. For generic HTTP rate limits or query errors, a model switch is not a general remedy.

## How to judge submit acceptance and terminal success

Do not rely on shell exit code alone.

For async generation commands, `submit_id` plus `gen_status=querying` means only that the submission was accepted. It is not evidence that generation finished successfully.

Treat the task as terminally successful only when `gen_status=success`. If `gen_status=fail`, inspect `fail_reason` and reply proactively with the concrete reason.

A query or polling error does not undo an accepted submission. Preserve its `submit_id` and last known state, report the query error separately, and continue by querying the same task. If command output is missing, inspect `list_task` before assuming the submission failed and creating another paid task.

Generation and query results may include `estimated_remaining_seconds`. This is the backend's current estimate, not a completion deadline:

- While the estimate is still positive, do not repeatedly call `query_result` in a tight loop. Normally wait until near the estimated time before checking again.
- If the user is waiting urgently or the result blocks the current task, query occasionally at a low frequency instead of every second.
- The estimate can move up or down, and the task may finish earlier or later. Only a terminal `gen_status` establishes the result; do not report the estimate as guaranteed.
- If the field is absent, the remaining time is unknown. Do not treat a missing value as zero.

Use `--poll=N` on a generation command to wait for up to N seconds for a terminal result. If the command still returns `querying` after that bounded wait:

- save the `submit_id`
- use `query_result --submit_id=<id>` for later follow-up; follow the long-wait rule below instead of keeping the conversation open indefinitely

If the estimated wait or the elapsed time since submission exceeds one hour, finish useful work that does not depend on that result, then end the current turn with a progress report. Do not wait an hour first when the backend already estimates several hours. Preserve the original generation requirements; unavailable tools or long queues do not justify replacing requested video performance with still images, narration or filler. Report the task ID, model, last known status, estimate when present, completed files, missing work, and the command needed to resume querying. Ending the turn leaves the accepted task pending; do not claim the requested deliverable is complete or promise automatic follow-up unless it has actually been arranged.

## Follow-up pattern for async tasks

After a submit returns `querying` without reaching a terminal result during `--poll=N`:

1. Save the `submit_id`.
2. If `estimated_remaining_seconds` is present, use it to avoid frequent follow-up queries; query at a low frequency only when an earlier result matters.
3. Use `query_result --submit_id=<id>` for follow-up. For a long wait, report pending work as described above; when work resumes, query the saved task before submitting anything new.
4. Add `--download_dir=<path>` when the completed media should be downloaded. The CLI resolves each file's download URL through Dreamina's download flow (the same as Dreamina Web) and prints it to stderr before downloading. If the built-in download fails, reuse that printed download URL with another downloader instead of resubmitting the generation task. If resolving the download URL fails, report the error and retry `query_result --download_dir` later; do not download the preview `image_url` / `video_url` instead.
5. Use `list_task` when you want to review saved tasks in bulk.

If you are running a test sweep, keep results in a machine-readable format so you can query the returned `submit_id` values later.

## Important user-facing rules

- Some generation commands are asynchronous; submit and query are separate steps.
- Some models may require a one-time authorization on Dreamina Web.
  If the CLI returns `AigcComplianceConfirmationRequired`, reply proactively: ask them to complete that web-side confirmation first, then retry.
- Do not assume that different commands support the same models, ratios, durations, or resolutions.
  Check each subcommand's `-h` before use.

## Good agent behavior

- Relay OAuth Device Flow instructions exactly enough for the user to complete login.
- Always close the loop when the login command finishes with a user-visible confirmation.
- Prefer small, reviewable batches when running real generation tasks.
- Keep a record of the command, arguments, `submit_id`, and final status for every paid test you run.
- If you are preparing a report, separate:
  - help-only inspection
  - submit-stage validation
  - later async result follow-up
