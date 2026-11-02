import "./tool.css";
import { PlanIntake } from "../plan-intake";

export const metadata = {
  title: "Check a plan · ConformScope",
  description: "Can a wheelchair live in this home? Measure every room, door and toilet on the plan.",
};

export default function CheckPage() {
  return <PlanIntake />;
}
