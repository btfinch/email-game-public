# Agent-to-Agent Communication Models: Centralized Hubs vs. Direct APIs

*Prepared for the Inbox-Arena project – July 2025*

---

## 1  Context and Motivation
Multi-agent systems (MAS) are moving from research demos to production-grade deployments spanning multiple organisations and clouds. A key design choice is **how agents exchange messages**:

1. **Direct API / Peer-to-Peer (P2P)** – every agent exposes its own HTTP/WS endpoints and talks to others directly.
2. **Broker / Hub** – traffic flows through one (or a small mesh of) hubs that handle routing, queueing, auth, and sometimes orchestration.

This document summarises industry efforts (Google **A2A**, IBM **ACP**, the community **Agent Protocol @Web**, Anthropic **MCP**) and recommends a direction for open, Internet-scale agent communications.

---

## 2  Snapshot of Existing Protocols

| Protocol | Origin | Architectural stance | Transport | Discovery | Session / State |
|----------|--------|----------------------|-----------|-----------|-----------------|
| **A2A** | Google (DeepMind / BardX, 2024) | *Peer-to-peer* autonomy. Agents publish *agent cards* (capabilities, policies) and negotiate tasks. | HTTP (REST); optional negotiation sub-protocol | Card search & filtering API | Stateless by default; long-lived conversations built ad-hoc |
| **ACP** | IBM (watsonx Orchestrate, 2023) | *Brokered* service bus. Agents/tools register with a central broker which manages workflow chains. | Message queues (Kafka/Rabbit) + HTTP callbacks | Central registry | Strong session tracking & audit |
| **Agent Protocol @Web** | Community (GitHub/agent-protocol, 2024) | *Hybrid*. Defines JSON schemas over HTTP/WebSocket; leaves topology open but recommends small hubs for scaling. | HTTP + WS + SSE | Simple `.well-known/ai-agent` endpoint or registry | Optional conversation IDs |
| **MCP** | Anthropic (Claude tool-use, 2023) | *Centralised* – planner/LLM is the single orchestrator calling "tools" (micro-agents). | Plain HTTP | None (configuration) | Stateless |

> See Enrico Piovesan, "How Agents Talk" for a broader comparison of MCP, A2A, ANP, ACP and others. [[medium](https://medium.com/software-architecture-in-the-age-of-ai/how-agents-talk-mapping-the-future-of-multi-agent-communication-protocols-6115ea083dba)]

---

## 3  Trade-off Matrix

| Criterion | Direct API / P2P | Central Hub / Broker |
|-----------|-----------------|----------------------|
| 🛠 **Operational Simplicity** | Each team must run a secure server (TLS, auth, scaling). | Only the hub is public; agents are outbound clients. |
| 🌐 **Network Reachability** | Fails behind NAT / firewalls without port-forwarding. | Works from any network – outbound HTTPS/WSS. |
| 🔒 **Security & Trust** | Many attack surfaces, uneven security postures. | Single ingress point → easier TLS, auth, rate-limit. |
| 📜 **Audit & Replay** | Logs scattered across N agents. | Complete traffic history in one place – vital for contests & compliance. |
| ⚖️ **Fairness & Rate-Limiting** | Hard to enforce globally. | Hub applies uniform limits, prevents spam/DOS. |
| 🔄 **Resilience** | Loss of one agent breaks only its links. | Hub is SPOF but can be HA with replicas + pub/sub. |
| 🔌 **Interoperability / Versioning** | Requires strict spec; divergent implementations common. | Hub can translate/validate messages centrally. |
| 📈 **Scalability (N agents)** | Up to N² connections; coordination overhead. | O(N) client connections; hub scales horizontally. |
| 🤖 **Emergent Autonomy** | Easier for agents to negotiate & self-organise (A2A style). | Hub can become bottleneck to fully autonomous swarms. |

---

## 4  Industry Direction

* **Enterprise & Regulated domains** (finance, healthcare): gravitating towards **brokered hubs** (IBM ACP style) for auditability, RBAC, and reliability.
* **Research & edge swarms** (IoT, robotics): experimenting with **peer autonomy** (A2A, Cisco ANP) but still add discovery overlays and TURN-style relays to traverse NAT.
* **AI assistant ecosystems** (OpenAI tools, Anthropic MCP): favour a **central orchestrator** for deterministic planning and simple developer onboarding.
* **Open-web initiatives** (Agent Protocol @Web): aiming for a *pluggable* middle ground – standard message schema + optional hubs.

Overall, we observe a **convergence toward small sets of federated hubs**:  
– keeps client implementation light,  
– preserves audit/security,  
– allows regional scaling (Edge Hub EU, Hub US),  
– still lets advanced agents establish direct channels when policies allow (e.g., upgrade to P2P after hub-mediated handshake).

---

## 5  Recommendation for Inbox-Arena-style Competitions

1. **Stick with a central email server** for the main gameplay – it mirrors ACP/MCP strengths and minimises participant DevOps burden.
2. **Add federated replicas** + Redis pub/sub for horizontal scale if >100 agents.
3. **Define a simple `.well-known/arena-agent.json`** description so future versions could support *optional* A2A-style direct negotiation without breaking the hub model.
4. **Monitor emerging standards**:
   * up-level message schema to Agent Protocol @Web JSON once stabilised.  
   * evaluate DID-based auth from ANP for cross-org identity.

This hybrid path delivers today while keeping the door open for more autonomous, decentralised agent swarms tomorrow.

---

## 6  References

1. Enrico Piovesan, "How Agents Talk: Mapping the Future of Multi-Agent Communication Protocols", *Medium*, June 2025. <https://medium.com/...how-agents-talk-6115ea083dba>
2. Google DeepMind, "A2A: Agent-to-Agent Communication Protocol", internal white-paper, 2024.
3. IBM Research, "ACP – Agent Communication & Planning Framework", 2023 white-paper.
4. Agent-Protocol @Web – GitHub project <https://github.com/agent-protocol/agent-protocol>.
5. Anthropic, "MCP: Metadata-Centric Protocol for Tool Use", technical blog, 2023.

---

## 7  Is There Room for a "Gmail for Agents"?

**Short answer: yes, but it will likely complement—not replace—today's mixed landscape.**

1. **Market forces**  
   • History shows that when a new communication medium emerges, hosted platforms lower the barrier to entry (Hotmail → email, Slack → team chat, Twilio → SMS).  
   • Many teams will prefer an *"agent mailbox as-a-service"* that handles identity, auth, persistence, and push delivery so they can focus on reasoning logic, not infra.

2. **What it would provide**  
   • Managed identity (DID / OIDC) and per-agent tokens  
   • Durable inbox + searchable history  
   • Multi-transport gateway (HTTP, WS, SSE, broker fan-out)  
   • Optional federation: similar to e-mail MX records, hubs relay across domains.

3. **Why it won't be the only model**  
   • Highly regulated orgs will self-host (analogous to on-prem Exchange).  
   • Edge/robotics swarms need local P2P for low-latency links.  
   • Some protocols (e.g., Google A2A) bake autonomy and negotiation into the agent layer—central relays would undercut those design goals.

4. **Realistic trajectory**  
   • Expect a few large "Agent Service Providers" (OpenAI, Google, AWS, Anthropic?) offering turnkey mailboxes + routing.  
   • Open-source hubs (Agent-Protocol compatible) will enable community and academic deployments.  
   • Over time, federation standards (Agent-SMTP?) may mirror e-mail's store-and-forward, letting hubs interoperate.

**Bottom line**: the *central hub pattern is already dominant* in early commercial offerings and will likely remain the default for ease-of-use and auditability.  A "Gmail for agents" is a natural evolution, but peer and edge scenarios ensure P2P APIs will also persist.  Designing protocols that support **both hub-mediated and direct channels** is therefore the most future-proof strategy. 

---

## 8  Current Vendor Offerings vs. Neutral Inboxes

While Section 7 covered the strategic outlook, teams often ask **"what can we use right now?"**

| Vendor / Product | How agents connect today | Hub-like capabilities | Real-time push exposed to user code? |
|------------------|--------------------------|-----------------------|-------------------------------------|
| **OpenAI – Assistants API / Threads** | Agents operate inside OpenAI's runtime; you call `POST /threads` & `POST /runs`. | Central store for messages, state, tool calls. | *Partial*: HTTP stream mode (SSE over HTTP/2), no generic WebSocket inbox. |
| **Anthropic – Claude Tool-use (MCP)** | Tools register via metadata; Claude calls them. | Claude acts as broker/orchestrator. | No – synchronous JSON calls only. |
| **Google – Vertex AI Agent Builder / App Builder** | Agents deploy to Vertex; orchestration & memory managed by Google. | Central store + routing. | Internal Pub/Sub; not exposed as WS inbox. |
| **IBM – watsonx Orchestrate (ACP)** | Skills/agents register with a broker; tasks flow through it. | Full session tracking, audit. | Enterprise tier can push over WebHooks/SSE; WS optional. |
| **Start-ups (LangSmith, Convex AgentBus, AutoGen Studio)** | Hosted hub you POST to; they fan-out to connected tools. | Inbox, identity, telemetry. | Many provide WebSockets for UI, but agents still poll or long-poll over HTTP. |

**Observation:** every major ecosystem has **its own proprietary hub**, but there is **no vendor-neutral "WebSocket inbox for any agent"** similar to e-mail's open MX federation.

That gap is why community standards such as **Agent-Protocol @Web** and DIY patterns (Redis pub/sub, Ably channels, Supabase Realtime) are popular stop-gaps—and why a turnkey "agent mailbox as-a-service" could gain adoption quickly. 