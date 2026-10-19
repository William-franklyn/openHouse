import { RoomClient } from "@/components/room/RoomClient";

export default async function RoomPage(props: PageProps<"/room/[id]">) {
  const { id } = await props.params;
  return <RoomClient roomId={id} />;
}
