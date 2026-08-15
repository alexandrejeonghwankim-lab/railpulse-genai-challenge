import pandas as pd
import chainlit as cl
from chainlit.input_widget import Select, Switch

from assistant import (
    AssistantError,
    UnsafeRequestError,
    answer_question,
)
from translations import (
    format_station_scope_message,
    get_ui_text,
    resolve_language,
)


MODE_VALUES = {
    "Latest Operations": "latest",
    "Historical Insights": "historical",
}

MAX_CONTEXT_TURNS = 2
MAX_CONTEXT_ROWS = 5

LANGUAGE_VALUES = {
    "Automatic (question language)": "auto",
    "Nederlands": "nl",
    "Français": "fr",
    "Deutsch": "de",
    "English": "en",
}


@cl.on_chat_start
async def on_chat_start():
    settings = await cl.ChatSettings(
        [
            Select(
                id="mode",
                label="RailPulse data mode",
                values=list(MODE_VALUES),
                initial_index=0,
            ),
            Select(
                id="language",
                label="Response language",
                values=list(LANGUAGE_VALUES),
                initial_index=0,
            ),
            Switch(
                id="show_technical_details",
                label="Show technical details",
                initial=False,
            ),
        ]
    ).send()

    selected_label = settings["mode"]
    cl.user_session.set(
        "mode",
        MODE_VALUES[selected_label],
    )
    cl.user_session.set(
        "show_technical_details",
        settings["show_technical_details"],
    )
    cl.user_session.set(
        "language",
        LANGUAGE_VALUES[settings["language"]],
    )
    cl.user_session.set(
        "conversation_contexts",
        {"latest": [], "historical": []},
    )
    cl.user_session.set("sql_messages", {})

    await cl.Message(
        content=(
            "RailPulse Consultant is ready.\n\n"
            "**Latest Operations** uses a fixed historical "
            "snapshot from 29 July through 4 August 2026. "
            "It is not a live feed."
        )
    ).send()

@cl.on_settings_update
async def on_settings_update(settings):
    selected_label = settings["mode"]
    mode = MODE_VALUES[selected_label]

    cl.user_session.set("mode", mode)
    cl.user_session.set(
        "show_technical_details",
        settings["show_technical_details"],
    )
    cl.user_session.set(
        "language",
        LANGUAGE_VALUES[settings["language"]],
    )

    await cl.Message(
        content=f"Data mode changed to **{selected_label}**."
    ).send()


@cl.action_callback("show_sql")
async def show_sql(action: cl.Action):
    sql = action.payload.get("sql")
    language = action.payload.get("language", "en")

    if not sql:
        await cl.Message(
            content=get_ui_text("no_sql", language)
        ).send()
        return

    sql_messages = cl.user_session.get("sql_messages") or {}
    existing_message = sql_messages.get(action.id)

    if existing_message:
        await existing_message.remove()
        del sql_messages[action.id]
        cl.user_session.set("sql_messages", sql_messages)
        return

    title = get_ui_text("validated_sql", language)
    sql_message = cl.Message(
        content=(
            f"**{title}**\n\n"
            f"```sql\n{sql}\n```"
        )
    )
    await sql_message.send()

    sql_messages[action.id] = sql_message
    cl.user_session.set("sql_messages", sql_messages)


@cl.on_message
async def on_message(message: cl.Message):
    mode = cl.user_session.get("mode") or "latest"
    conversation_contexts = cl.user_session.get(
        "conversation_contexts"
    ) or {"latest": [], "historical": []}
    conversation_context = conversation_contexts.get(mode, [])
    show_technical_details = cl.user_session.get(
        "show_technical_details"
    ) or False
    requested_language = cl.user_session.get("language") or "auto"
    response_language = resolve_language(
        requested_language,
        message.content,
    )

    try:
        result = await cl.make_async(answer_question)(
            mode,
            message.content,
            language=requested_language,
            conversation_context=conversation_context,
        )
    except UnsafeRequestError:
        await cl.Message(
            content=get_ui_text(
                "unsafe_request",
                response_language,
            )
        ).send()
        return
    except AssistantError:
        await cl.Message(
            content=get_ui_text(
                "request_error",
                response_language,
            )
        ).send()
        return
    except Exception:
        await cl.Message(
            content=get_ui_text(
                "service_error",
                response_language,
            )
        ).send()
        return

    elements = []
    result_language = result.get("language", response_language)

    if result["status"] == "success":
        conversation_context.append(
            {
                "question": result["question"],
                "validated_sql": result["sql"],
                "database_rows": result["rows"][:MAX_CONTEXT_ROWS],
            }
        )
        conversation_contexts[mode] = conversation_context[
            -MAX_CONTEXT_TURNS:
        ]
        cl.user_session.set(
            "conversation_contexts",
            conversation_contexts,
        )

    if result["rows"]:
        dataframe = pd.DataFrame(result["rows"])

        elements.append(
            cl.Dataframe(
                name=get_ui_text(
                    "query_results",
                    result_language,
                ),
                data=dataframe,
                display="inline",
            )
        )

    if show_technical_details and result["sql"]:
        elements.append(
            cl.Text(
                name=get_ui_text(
                    "validated_sql",
                    result_language,
                ),
                content=result["sql"],
                language="sql",
                display="side",
            )
        )

    actions = []

    if result["sql"]:
        actions.append(
            cl.Action(
                name="show_sql",
                label=get_ui_text(
                    "show_sql",
                    result_language,
                ),
                icon="code",
                payload={
                    "sql": result["sql"],
                    "language": result_language,
                },
            )
        )

    display_answer = result["answer"]
    station_scope = result.get("station_scope")

    if station_scope:
        scope_message = format_station_scope_message(
            station_scope["localized_stations"],
            result_language,
        )
        display_answer = (
            f"_{scope_message}_\n\n"
            f"{display_answer}"
        )

    await cl.Message(
        content=display_answer,
        elements=elements,
        actions=actions,
    ).send()
