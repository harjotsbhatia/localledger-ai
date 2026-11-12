import { ModelSetup } from "../components/ModelSetup";
import { PageHeader } from "../components/ui";

export function ModelScreen() {
  return (
    <div className="max-w-3xl">
      <PageHeader
        title="Local AI"
        subtitle="The assistant uses a language model running in Ollama on this Mac. Your questions and transactions are not sent to a cloud AI service."
      />
      <ModelSetup />
    </div>
  );
}
