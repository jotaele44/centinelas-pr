import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { getWaterDisruptionConsole } from "@/api/pipelineClient";
import WaterDisruption from "./WaterDisruption";

vi.mock("@/api/pipelineClient", () => ({
  getWaterDisruptionConsole: vi.fn(),
}));

describe("WaterDisruption", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("embeds the backend HTML console with an accessible title", async () => {
    getWaterDisruptionConsole.mockResolvedValue({
      available: true,
      url: "http://localhost:8000/water-disruption/console",
    });

    render(<WaterDisruption />);

    const frame = await screen.findByTitle("Water disruption shadow console");
    expect(frame).toHaveAttribute(
      "src",
      "http://localhost:8000/water-disruption/console",
    );
  });

  it("shows a safe unavailable state and supports retry", async () => {
    getWaterDisruptionConsole
      .mockResolvedValueOnce({
        available: false,
        url: "http://localhost:8000/water-disruption/console",
      })
      .mockResolvedValueOnce({
        available: true,
        url: "http://localhost:8000/water-disruption/console",
      });

    render(<WaterDisruption />);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Water disruption console unavailable",
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Retry loading water disruption console",
      }),
    );

    await waitFor(() => {
      expect(getWaterDisruptionConsole).toHaveBeenCalledTimes(2);
    });
    expect(
      await screen.findByTitle("Water disruption shadow console"),
    ).toBeInTheDocument();
  });
});
