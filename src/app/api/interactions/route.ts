import { type NextRequest, NextResponse } from "next/server";
import { z } from "zod";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";

const EventSchema = z.object({
  id: z.string(),
  type: z.string(),
  timestamp: z.number(),
  tabId: z.number(),
  windowId: z.number(),
  url: z.string().optional(),
  title: z.string().optional(),
  payload: z.record(z.any()), // Flexible payload structure
});

const BatchSchema = z.object({
  events: z.array(EventSchema),
  timestamp: z.number(),
});

export async function POST(request: NextRequest) {
  try {
    const body: unknown = await request.json();

    const batch = BatchSchema.parse(body);

    const venvPython = path.join(
      process.cwd(),
      "src/server/python/venv/bin/python",
    );
    const pythonExecutable = fs.existsSync(venvPython) ? venvPython : "python3";

    const pythonProcess = spawn(
      pythonExecutable,
      [
        path.join(process.cwd(), "src/server/python/group_flows.py"),
        JSON.stringify(batch),
      ],
      {
        cwd: path.join(process.cwd(), "src/server/python"),
        stdio: ["pipe", "pipe", "pipe"],
      },
    );

    // Set up output piping without waiting for completion
    pythonProcess.stdout?.on("data", (data: Buffer) => {
      const dataString = data.toString();
      console.log(`[Python stdout]: ${dataString}`);
    });

    pythonProcess.stderr?.on("data", (data: Buffer) => {
      const dataString = data.toString();
      console.error(`[Python stderr]: ${dataString}`);
    });

    pythonProcess.on("close", (code) => {
      console.log(`[Python process] Exited with code: ${code}`);
    });

    pythonProcess.on("error", (error) => {
      console.error(`[Python process] Error: ${error.message}`);
    });

    // Return immediately with success
    return NextResponse.json({
      success: true,
      message: "Processing started in background",
    });
  } catch (error) {
    console.error("Error processing request:", error);

    if (error instanceof z.ZodError) {
      console.log("Validation errors:", error.errors);
      return NextResponse.json(
        { error: "Invalid payload", details: error.errors },
        { status: 400 },
      );
    }

    return NextResponse.json(
      { error: "Internal server error" },
      { status: 500 },
    );
  }
}
