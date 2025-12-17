# Tutorial

Welcome to the Interlock tutorial! This step-by-step guide will teach you how to build event-sourced applications using CQRS patterns.

## What You'll Build

Throughout this tutorial, you'll build a **Bank Account** application that demonstrates:

- Creating and managing aggregates
- Handling commands and emitting events
- Processing events to build read models
- Using middleware for cross-cutting concerns
- Structuring your application with conventions

## Prerequisites

- Python 3.10+
- Basic understanding of async/await
- Familiarity with Pydantic is helpful but not required

## Tutorial Sections

| Section | Description |
|---------|-------------|
| [Your First Aggregate](01-your-first-aggregate.md) | Create a domain aggregate that manages state |
| [Commands & Handlers](02-commands-and-handlers.md) | Define commands and handle them in aggregates |
| [Events & Sourcing](03-events-and-sourcing.md) | Emit events and rebuild state from event history |
| [Event Processors](04-event-processors.md) | React to events and build read models |
| [Middleware](05-middleware.md) | Add logging, idempotency, and more |
| [Structuring Your Application](06-structuring-the-application.md) | Organize your code with conventions |
| [Putting It Together](07-putting-it-together.md) | Build a complete application |

## Getting Help

If you get stuck:

- Check the [Concepts](../concepts/index.md) section for deeper explanations
- Browse the [API Reference](../reference/index.md) for detailed documentation
- Open an issue on [GitHub](https://github.com/interlock-proj/interlock/issues)

Ready? Let's start with [Your First Aggregate](01-your-first-aggregate.md)!

