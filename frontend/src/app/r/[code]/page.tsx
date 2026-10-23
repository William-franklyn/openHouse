import { JoinClient } from "@/components/join/JoinClient";

export default async function JoinPage(props: PageProps<"/r/[code]">) {
  const { code } = await props.params;
  const searchParams = await props.searchParams;
  const inviteParam = searchParams.invite;
  const invitePrefill = Array.isArray(inviteParam) ? inviteParam[0] : inviteParam;
  return <JoinClient code={code.toUpperCase()} invitePrefill={invitePrefill ?? null} />;
}
