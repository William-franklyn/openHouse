import { JoinClient } from "@/components/join/JoinClient";

export default async function JoinPage(props: PageProps<"/r/[code]">) {
  const { code } = await props.params;
  return <JoinClient code={code.toUpperCase()} />;
}
