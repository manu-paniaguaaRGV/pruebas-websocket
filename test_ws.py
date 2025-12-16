from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from typing import TypedDict, Literal
import asyncio # Importamos asyncio para usar sleep no bloqueante
from langgraph.graph import StateGraph, START, END
import json

# --- LangGraph ---

# definicion del state
class AgentState(TypedDict):
    """The state of the agent in LangGraph."""
    user_message: str
    plan_needed: Literal["yes", "no"]
    execution_complete: bool
    final_answer: str

# definicion de los nodos
async def plan_step(state: AgentState):
    """Generates a plan based on the user's message."""
    # simular tiempo de pensamiento/ejecucion LLMs
    await asyncio.sleep(0.5) 
    
    # checar las palabras clave para determinar si se necesita ejecutar un plan
    if "simular" in state["user_message"].lower() or "ejecutar" in state["user_message"].lower():
        plan_needed = "yes"
    else:
        plan_needed = "no" # Simple response needed

    return {"plan_needed": plan_needed}

async def execute_step(state: AgentState):
    """Simulates the execution of a complex task."""
    # simula una tara larga de ejecucion
    await asyncio.sleep(3) 
    
    # simula el resultado
    result = f"La simulación de la tarea solicitada ('{state['user_message']}') ha concluido con éxito tras 3 segundos de cálculo."
    return {"execution_complete": True, "final_answer": result}

async def check_result_step(state: AgentState):
    """Checks the result and finalizes the answer."""
    # simula el procesamiento del LLM
    await asyncio.sleep(0.5) 

    # This node finalizes the answer
    if state["execution_complete"]:
        final_answer = f"Tarea Completa: {state['final_answer']}. El agente ha terminado su ciclo de trabajo."
    else:
        # If no execution was needed
        final_answer = f"Respuesta Rápida: No se requirió ejecución compleja para: '{state['user_message']}'. Proceso terminado."
    return {"final_answer": final_answer}

def route_plan(state: AgentState):
    """Conditional edge to route based on plan_needed."""
    return state["plan_needed"]

# construccion del grafo
graph = (
    StateGraph(AgentState)
    .add_node("plan", plan_step)
    .add_node("execute", execute_step)
    .add_node("check_result", check_result_step)
    .add_edge(START, "plan")
    .add_conditional_edges("plan", route_plan, {
        "yes": "execute",
        "no": "check_result"
    })
    .add_edge("execute", "check_result")
    .set_finish_point("check_result")
    .compile()
)

# --- Generador de streaming (SSE) ---
async def agent_streamer(prompt: str):
    """
    Generador que ejecuta el LangGraph y envía cada paso como un evento SSE.
    """
    # entrada del usuario como state
    inputs = {"user_message": prompt, "execution_complete": False}
    
    # configuracion de LangGraph (se requiere un thread_id)
    config = {"configurable": {"thread_id": "sse_session"}}

    # ejecutar el grafo y streamear los "chunks"
    async for chunk in graph.astream(inputs, config=config): # Usamos 'astream' para nodos asíncronos
        
        # LangGraph devuelve un diccionario con el nodo actual
        node_name = list(chunk.keys())[0]
        
        # determinar el mensaje a enviar al cliente
        if node_name == START:
            message = "--- Agente Iniciado: Comenzando el Flujo de Trabajo ---"
        elif node_name == "plan":
            message = "**Paso 1: [PLANIFICACIÓN].** Analizando la solicitud del usuario..."
            yield f"data: {message}\n\n"
            # retraso para ver el mensaje de "Analizando" antes de que se complete el paso
            await asyncio.sleep(0.5) 
        elif node_name == "execute":
            message = "**Paso 2: [EJECUCIÓN].** Se detectó tarea compleja. Iniciando simulación de 3 segundos..."
            yield f"data: {message}\n\n"
            # retraso de 3 segundos se ejecuta dentro del nodo 'execute_step', pero podemos añadir
            # un pequeño retraso aquí también para asegurarnos de que el mensaje 'Iniciando' se envíe.
            await asyncio.sleep(0.5) 
        elif node_name == "check_result":
            message = "**Paso 3: [VERIFICACIÓN].** Recopilando y formateando la respuesta final."
            yield f"data: {message}\n\n"
            await asyncio.sleep(0.5)

    # obtener y enviar el resultado final despues de que el bucle `astream` termine
    try:
        final_state = await graph.ainvoke(inputs, config=config) # Usamos 'ainvoke' para obtener el estado final
        final_answer = final_state.get('final_answer', 'Error: No se generó respuesta final.')
        yield f"data: **[RESULTADO FINAL DEL AGENTE]** {final_answer}\n\n"
    except Exception as e:
        yield f"data: **[ERROR FATAL]** Fallo al obtener el estado final. {str(e)}\n\n"
    # enviar un mensaje de fin de stream, incluso si ahy errores
    finally:
        yield f"data: --- FIN DEL STREAM ---\n\n"

# --- FastAPI ---

app = FastAPI(title="LangGraph Agent Streaming")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



@app.get("/stream")
async def stream_endpoint(prompt: str):
    """Endpoint que acepta un prompt y devuelve un StreamingResponse (SSE)."""
    if not prompt:
        # Manejo de errores si no hay prompt
        return StreamingResponse(
            iter([f"data: ERROR: No se proporcionó ningún prompt.\n\n"]),
            media_type="text/event-stream"
        )
    


    # with open("output.json", "r", encoding="utf-8") as f:
    #     data = json.load(f)

    # json_sse = f"data: {json.dumps(data)}\n\n"

    
    # return StreamingResponse(
    #     iter([json_sse]),
    #     media_type="text/event-stream",
    #     headers={
    #         "Access-Control-Allow-Origin": "*",
    #         "Access-Control-Allow-Headers": "*",
    #         "Access-Control-Allow-Methods": "*",
    #         "Cache-Control": "no-cache",
    #         "Connection": "keep-alive",
    #     },
    # )


    # Devuelve el generador SSE
    return StreamingResponse(
        agent_streamer(prompt), 
        media_type="text/event-stream",
        headers={
            "Access-Control-Allow-Origin": "*",  
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Allow-Methods": "*",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )