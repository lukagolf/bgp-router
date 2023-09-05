#!/usr/bin/env python3

import argparse, socket, json, select
from copy import deepcopy

class Router:
    """
    Represents a router in a network.

    Attributes
    ----------
    asn : str
        The ASN number of this router.
    connections : list
        A list of routers that this router is directly connected to (AKA the neighbors).
    sockets : dict
        Collection of sockets for each neighbor in the connections list.
    ports : dict
        Dictionary of ports for each neighbor.
    updates : list
        BGP updates recieved by this router.
    routes : list
        Route forwarding table of this router.
    """

    relations = {}
    sockets = {}
    ports = {}
    updates = []
    routes = []

    def __init__(self, asn, connections):
        print("Router at AS %s starting up" % asn)
        self.asn = asn
        for relationship in connections:
            port, neighbor, relation = relationship.split("-")

            self.sockets[neighbor] = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sockets[neighbor].bind(('localhost', 0))
            self.ports[neighbor] = int(port)
            self.relations[neighbor] = relation
            self.send(neighbor, json.dumps({ "type": "handshake", "src": self.our_addr(neighbor), "dst": neighbor, "msg": {}  }))

    def our_addr(self, dst):
        """
        Returns the IP address of this router based on the given destination address.
        """
        quads = list(int(qdn) for qdn in dst.split('.'))
        quads[3] = 1
        return "%d.%d.%d.%d" % (quads[0], quads[1], quads[2], quads[3])

    def send(self, network, message):
        """
        Sends the given message to the given network address.
        """
        self.sockets[network].sendto(message.encode('utf-8'), ('localhost', self.ports[network]))
    
    def ip_to_binary_string(self,ip):
        """
        Converts an IP address to its corresponding binary representation.
        """
        bin_ip = ""
        segments=ip.split(".")
        for segment in segments:
            bin_ip += '{0:08b}'.format(int(segment))
        return bin_ip

    def netmask_with_length(self, netmask_length):
        """
        Return netmask for a given netmask length.
        """
        ip=""
        for i in range(0,4):
            segment = 8
            if netmask_length < 8:
                segment = netmask_length
                netmask_length = 0
            else:
                netmask_length -= 8 
            segment = 2**8 - 2**(8 - segment)
            ip += "." + str(segment)
        return ip[1:]

    def get_netmask_length(self, netmask):
        """ Returns the length of the given net mask. """
        return self.ip_to_binary_string(netmask).count('1')

    def aggregate_routes(self, route1, route2):
        """ 
        Tries to aggregate the given 2 routes based on netmask, localpref, origin, and AS path.
        """
        if(route1["netmask"]!= route2["netmask"] or route1["localpref"]!= route2["localpref"] 
            or route1["selfOrigin"]!= route2["selfOrigin"] or route1["ASPath"]!= route2["ASPath"]
            or route1["origin"]!= route2["origin"]):
            return None

        netmask_length = self.get_netmask_length(route1["netmask"])
        route1_ip_binary = self.ip_to_binary_string(route1["network"])
        route2_ip_binary = self.ip_to_binary_string(route2["network"])
        if( route1_ip_binary[0: (netmask_length -1)] !=  route2_ip_binary[0: (netmask_length -1)]
            or route1_ip_binary[netmask_length -1] ==  route2_ip_binary[netmask_length -1]):
            return None    

        aggregated_route = deepcopy(route1)
        if route1["network"] > route2["network"]:
            aggregated_route["network"] = route2["network"]
            aggregated_route["child0"] = route2
            aggregated_route["child1"] = route1
        else:
            aggregated_route["child0"] = route1
            aggregated_route["child1"] = route2
        aggregated_route["netmask"] = self.netmask_with_length(netmask_length - 1)
        return aggregated_route

    def coalesce(self):
        """
        Performs route aggregation on the entire routes table.
        """
        aggregated_routes = []
        for i in range(0, len(self.routes)):
            for j in range(i + 1, len(self.routes)):
                aggregated_route = self.aggregate_routes(self.routes[i], self.routes[j])
                if aggregated_route is not None:
                    aggregated_routes.append({"route1": self.routes[i], "route2": self.routes[j], "aggregated_route": aggregated_route})
        for route in aggregated_routes:
            self.routes.remove(route["route1"])
            self.routes.remove(route["route2"])
            self.routes.append(route["aggregated_route"])
        if len(aggregated_routes) > 0:
            return self.coalesce()

    def handle_update_msg(self, srcif, msg):
        """
        Handles a BGP update message.
        """
        self.updates.append(msg)
        new_route = deepcopy ( msg["msg"])
        new_route["peer"] = msg["src"]
        new_route["child0"] = None
        new_route["child1"] = None

        self.routes.append(new_route)
        self.coalesce()

        n_msg = {}
        n_msg["msg"] = {'netmask': msg["msg"]["netmask"], 'ASPath': [self.asn]+msg["msg"]["ASPath"], 'network':msg["msg"]["network"]}
        n_msg["type"] = "update"
        for neighbor in self.relations.keys():
            if neighbor!=srcif and (self.relations[srcif]=="cust" or self.relations[neighbor]=="cust"):
                n_msg["src"] = self.our_addr(neighbor)
                n_msg["dst"] = neighbor
                self.send(neighbor, json.dumps(n_msg))
        

    def withdraw_route(self, srcif, withdraw_msg, route):
        """
        Checks if the given route should be withdrawn based on the given BGP message.
        """
        if (route["network"] == withdraw_msg["network"] and 
            route["netmask"] == withdraw_msg["netmask"] and 
            route["peer"] == srcif):
                # Return true if network, netmask, and peer are the same
                return True
        elif not(route["child0"] is None):
            if self.withdraw_route(srcif, withdraw_msg, route["child0"]):
                if not (route["child1"] in self.routes):
                    self.routes.append(route["child1"])
                return True 
            elif self.withdraw_route(srcif, withdraw_msg, route["child1"]):
                if not (route["child0"] in self.routes):
                    self.routes.append(route["child0"])
                return True 
        return False

    def handle_withdraw_msg(self, srcif, msg):
        """
        Handles a BGP withdraw message.
        """
        self.updates.append(msg)
        withdraw_routes = []
        for route in self.routes:
            for withdraw_msg in msg["msg"]:
                if self.withdraw_route(srcif, withdraw_msg, route):
                    withdraw_routes.append(route)

        # For each route to be withdrawn, remove it from self.routes if its in it.
        for withdraw_route in withdraw_routes: 
            if withdraw_route in self.routes:
                self.routes.remove(withdraw_route)   

        # For each neighbor that is a cusomer, send them the withdraw message.
        for neighbor in self.relations.keys():
            if neighbor!=srcif and (self.relations[srcif]=="cust" or self.relations[neighbor]=="cust"):
                msg["src"] = self.our_addr(neighbor)
                msg["dst"] = neighbor
                self.send(neighbor, json.dumps(msg))
        return

    def find_routes(self, srcif, dest):
        """
        Finds a route to the given destination address.
        """
        valid_routes = []
        valid_netmask_length = -1

        # Goes through the routing table and decides which addresses will route to the given destination.
        for route in self.routes:
            netmask_length = self.get_netmask_length(route["netmask"])
            if self.ip_to_binary_string(dest)[0:netmask_length] == self.ip_to_binary_string(route["network"])[0:netmask_length]:
                if valid_netmask_length < netmask_length:
                    valid_netmask_length = netmask_length
                    valid_routes = [route]
                elif valid_netmask_length == netmask_length:
                    if valid_routes[0]["localpref"] < route["localpref"]:
                        valid_netmask_length = netmask_length
                        valid_routes = [route]
                    elif valid_routes[0]["localpref"] == route["localpref"]:
                        if (not valid_routes[0]["selfOrigin"]) and route["selfOrigin"]:
                            valid_netmask_length = netmask_length
                            valid_routes = [route]
                        elif valid_routes[0]["selfOrigin"] == route["selfOrigin"]:
                            if len(valid_routes[0]['ASPath']) > len(route["ASPath"]):
                                valid_netmask_length = netmask_length
                                valid_routes = [route]
                            elif len(valid_routes[0]['ASPath']) == len(route["ASPath"]):
                                v_origin = valid_routes[0]['origin']
                                origin = route["origin"]
                                if (origin == "IGP" and v_origin != "IGP") or (origin =="EGP" and v_origin =="UNK"):
                                    valid_netmask_length = netmask_length
                                    valid_routes = [route]
                                elif origin==v_origin:
                                    if valid_routes[0]['peer']> route['peer']:
                                        valid_netmask_length = netmask_length
                                        valid_routes = [route]
                                    elif valid_routes[0]['peer']> route['peer']:
                                        valid_routes.append(route)


        # After getting the valid routes, we filter the baed on whether the route goes to a customer or not.
        filtered_valid_routes = valid_routes
        if self.relations[srcif] != "cust":
            filtered_valid_routes = []
            for route in valid_routes:
                if self.relations[route["peer"]] == "cust":
                    filtered_valid_routes.append(route)

        if len(filtered_valid_routes) == 0:
            return None

        return filtered_valid_routes[0]


    def handle_data_msg(self, srcif, msg):
        """
        Handles a BGP data message.
        """

        # Find the route to the destination in the message.
        route = self.find_routes(srcif, msg["dst"])
        if route is None:
            # Send a no route meessage back to the src if we have no way to get to the destination.
            self.send(srcif, json.dumps({ "type": "no route", "src": self.our_addr(srcif), "dst": msg["src"], "msg": {}  }))
        else:
            # Else, send the message if we have a path.
            self.send(route["peer"], json.dumps(msg))

    def handle_dump_msg(self, msg):
        """
        Handles a dump table message.
        """
        printable_routes = deepcopy(self.routes)
        for printable_route in printable_routes:
            printable_route.pop("child0")
            printable_route.pop("child1")

        self.send(msg["src"], json.dumps({"type": "table", "src": msg["dst"], "dst": msg["src"], "msg": printable_routes}))      
      
    def handle_msg(self, srcif, msg):
        """
        BGP message handler. Dispatches the appropriate helper function based on the message type.
        """
        if msg["type"] == "update":
            self.handle_update_msg(srcif, msg)
        elif msg["type"] == "withdraw":
            self.handle_withdraw_msg(srcif, msg)
        elif msg["type"] == "data":
            self.handle_data_msg(srcif, msg)
        elif msg["type"] == "dump":
            self.handle_dump_msg(msg)

    def run(self):
        """
        Starts up this router.
        """
        while True:
            socks = select.select(self.sockets.values(), [], [], 0.1)[0]
            for conn in socks:
                k, addr = conn.recvfrom(65535)
                srcif = None
                for sock in self.sockets:
                    if self.sockets[sock] == conn:
                        srcif = sock
                        break
                msg = json.loads(k)

                print("Received message '%s' from %s" % (msg, srcif))
                self.handle_msg(srcif, msg)

        return

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='route packets')
    parser.add_argument('asn', type=int, help="AS number of this router")
    parser.add_argument('connections', metavar='connections', type=str, nargs='+', help="connections")
    args = parser.parse_args()
    router = Router(args.asn, args.connections)
    router.run()
